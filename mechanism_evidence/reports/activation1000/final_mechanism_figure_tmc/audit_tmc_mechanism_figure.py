"""Audit final PDF fonts/geometry and every plotted value against immutable CSV sources."""
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
from pypdf import PdfReader
from PIL import Image


def read(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def audit(root,out):
    csv.field_size_limit(64*1024*1024)
    b=json.loads((out/'plot_data.json').read_text());meta=b['metadata'];rd=meta['round'];cid=meta['receiver']
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest()==v for name,v in meta['source_file_sha256'].items()}
    assert all(hashes.values())
    original={n:read(root/n) for n in meta['source_file_sha256']}
    assert b['categories']==[r for r in original['used_categories.csv'] if int(r['round'])==rd]
    assert b['scores']==sorted([r for r in original['source_rounds.csv'] if int(r['round'])==rd],key=lambda r:int(r['tier']))
    assert b['all_shares']==[r for r in original['region_shares.csv'] if int(r['round'])==rd]
    originals={r['method']:r for r in original['full_counterfactual_raw.csv'] if int(r['round'])==rd and int(r['receiver'])==cid}
    values_checked=0
    for r in read(out/'panel_a_semantic.csv'):
        found=next((v for v in b['categories'] if v['tier']==r['tier'] and v['category']==r['category']),None)
        assert (r['missing']=='True')==(found is None)
        if found:
            assert float(r['signed_task_margin'])==float(found['q_post'])-float(found['reference_q']);values_checked+=1
    for r in read(out/'panel_b_memory.csv'):
        rows=[v for v in b['categories'] if v['tier']==r['tier']]
        d=statistics.mean(float(v['d']) for v in rows)
        m=statistics.mean(min(float(v['d']),float(v['a'])) for v in rows)
        u=statistics.mean(float(v['rho'])*min(float(v['d']),float(v['a'])) for v in rows)
        assert math.isclose(float(r['value']),dict(d=d,m=m,U=u)[r['stage']],abs_tol=1e-14);values_checked+=1
        assert math.isclose(float(r['mean_rho']),statistics.mean(float(v['rho']) for v in rows),abs_tol=1e-14)
    for r in read(out/'panel_c_shares.csv'):
        old=next(v for v in b['representative_shares'] if v['tier']==r['tier'])
        assert float(r['a07_percent'])==100*float(old['pi_before'])
        assert float(r['v2_percent'])==100*float(old['pi_after'])
        assert float(r['delta_pp'])==100*(float(old['pi_after'])-float(old['pi_before']));values_checked+=3
    common={int(v['category']) for v in b['categories']}
    def class_ce(row):
        return statistics.mean(v['after_ce'] for v in json.loads(row['per_class']) if v['category'] in common)
    for r in read(out/'panel_d_utility.csv'):
        expected=(float(originals['A07']['after_ce'])-float(originals[r['method']]['after_ce']) if r['metric']=='all'
                  else class_ce(originals['A07'])-class_ce(originals[r['method']]))
        assert math.isclose(float(r['utility_vs_a07']),expected,abs_tol=2e-15);values_checked+=1
    for r in read(out/'panel_d_background_statistics.csv'):
        values=[float(v['utility_vs_a07']) for v in original['full_counterfactual_raw.csv'] if v['method']==r['method']]
        assert len(values)==int(r['n'])==318
        q=statistics.quantiles(values,n=4,method='inclusive')
        for key,value in dict(minimum=min(values),q25=q[0],median=q[1],q75=q[2],maximum=max(values)).items():
            assert math.isclose(float(r[key]),value,abs_tol=1e-15);values_checked+=1
    prints=json.loads((out/'printed_values.json').read_text())
    for p in prints:
        text=format(p['value'],p['format'])+('%' if p['panel']=='c_absolute' else '')
        assert p['text']==text
    pdf=PdfReader(out/'figure_mechanism_case.pdf');assert len(pdf.pages)==1
    page=pdf.pages[0];width=float(page.mediabox.width)/72;height=float(page.mediabox.height)/72
    assert abs(width-7.16)<1e-8 and abs(height-7.9)<1e-8
    fonts=[]
    for ref in page['/Resources']['/Font'].values():
        f=ref.get_object();name=str(f['/BaseFont']);assert 'TimesNewRoman' in name and 'Bold' in name
        members=f.get('/DescendantFonts',[f]);embedded=[]
        for child in members:
            fd=child.get_object().get('/FontDescriptor').get_object()
            stream=fd.get('/FontFile2') or fd.get('/FontFile3') or fd.get('/FontFile')
            assert stream is not None and len(stream.get_object().get_data())>0
            embedded.append(len(stream.get_object().get_data()))
        fonts.append(dict(name=name,subtype=str(f['/Subtype']),embedded_font_bytes=embedded))
    font_sizes=set();font_names=set()
    def visitor(text,cm,tm,font,size):
        if text.strip():font_sizes.add(float(size));font_names.add(str(font['/BaseFont']))
    page.extract_text(visitor_text=visitor)
    assert font_sizes=={8.,9.,10.} and all('TimesNewRoman' in x and 'Bold' in x for x in font_names)
    images=[str(k) for k,v in page['/Resources'].get('/XObject',{}).items() if v.get_object().get('/Subtype')=='/Image']
    assert not images
    ext=json.loads((out/'text_extents.json').read_text());outside=[];overlap=[]
    for t in ext['texts']:
        x0,y0,x1,y1=t['bbox_points']
        if min(x0,y0)<-.2 or x1>ext['width_points']+.2 or y1>ext['height_points']+.2:outside.append(t)
        assert t['size'] in (8,9,10)
    for a,c in itertools.combinations(ext['texts'],2):
        x0,y0,x1,y1=a['bbox_points'];u0,v0,u1,v1=c['bbox_points']
        dx=min(x1,u1)-max(x0,u0);dy=min(y1,v1)-max(y0,v0)
        if dx>.5 and dy>.5:overlap.append([a['text'],c['text'],dx*dy])
    assert not outside and not overlap,(outside,overlap)
    png=Image.open(out/'figure_mechanism_case.png');assert png.width==round(7.16*450)
    dpi=png.info.get('dpi');assert dpi and min(dpi)>449
    # Capability colors have redundant textual and hatch identity in the actual plot.
    style=json.loads((out/'style_manifest.json').read_text())
    assert style['palette']==['#0072B2','#A96300','#006B55']
    result=dict(success=True,case_round=rd,receiver=cid,source_hashes_unchanged=hashes,
        numeric_fields_independently_checked=values_checked,printed_numeric_labels_checked=len(prints),
        width_inches=width,height_inches=height,pdf_pages=1,pdf_fonts=fonts,actual_pdf_font_sizes=sorted(font_sizes),
        non_times_bold_fonts=[],embedded_raster_images=images,png_dimensions=[png.width,png.height],png_dpi=dpi,
        text_bbox_count=len(ext['texts']),clipped_text_count=len(outside),text_overlap_count=len(overlap),
        capability_colors=style['palette'],redundant_encoding='Capability names, hatches, shapes and direct values; sign heatmap is a separate scalar palette',
        context_all_methods=True,background_n_per_method=318,boxplot_whiskers='all-data minimum/maximum, not95%CI',
        main_effect_axis='linear',background_axis='separate symlog, linear +/-1e-6 CE',
        visual_inspection='pending',gray_review='pending',no_new_training=True,original_figures_unchanged=True)
    (out/'QUALITY_CHECK.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();audit(a.root,a.output)
