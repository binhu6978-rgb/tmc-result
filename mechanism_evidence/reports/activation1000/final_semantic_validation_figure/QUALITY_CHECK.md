# Figure quality check

- Final width: 7.16 inches; height: 4.35 inches.
- Vector PDF: 1 page, no raster image objects.
- Actual embedded font: TimesNewRomanPS-BoldMT, Type0, 41,560 embedded bytes.
- Actual PDF text sizes: exactly 8, 9 and 10 pt.
- PNG: 3222 x 1957 pixels, 450 dpi.
- All 40 visible text objects inside canvas; 0 detected overlaps, 0 clipping.
- Reviewed PDF renders at 96 dpi (actual display width) and 170 dpi; grayscale reviewed.
- Capability colors have redundant circle/square/triangle identity; method curves have distinct markers and dash styles.
- All 15,288 exported raw fields checked against the original CSV; 392 common-class utilities recomputed from class records; 50 source-round utilities and all 40 curve points recomputed independently.
- All four original evidence hashes unchanged. No old figures overwritten, no new training.
- Four targeted tests passed in 0.92 seconds.
- Statistical limits: outcome-selected subset, conditional intervals, dependence across recurring clients and training stages; no claim of stable causal Memory gain.

Recheck PDF and values with `python tools/audit_semantic_validation_figure.py docs/evidence/semantic_a07_v2/activation1000/results docs/evidence/semantic_a07_v2/activation1000/final_semantic_validation_figure` using a Python with pypdf and Pillow. Re-running this audit sets manual visual-review fields to pending; perform the visual checks again after any plot change.
