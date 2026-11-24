#!/usr/bin/env python3
"""Write social-preview.svg (1280x640) from figure-data.json.

Render with headless Chrome at scale 1:
  chrome --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1280,640 --screenshot=assets/social-preview.png assets/header/social-preview.svg
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "figure-data.json").read_text())
W, H, PAD = 1280, 640, 96
INK, MUTED, FAINT = "#141413", "#55544f", "#6b6a65"
SURFACE, TRACK, ACCENT, BASELINE = "#fcfcfb", "#ebeae5", "#2a78d6", "#8f8e88"
FONT = "-apple-system, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"


def text(x, y, content, size, color=INK, weight=400, anchor="start", spacing=0):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}"{extra}>{escape(content)}</text>')


rubq = DATA["rubq"]
total = rubq["queries"]
rows = [
    ("Yuanbao-Reranker-0.6B Q8_0", None, rubq["models"]["yuanbao-q8"], ACCENT, INK),
    ("Qwen3-Reranker-0.6B Q8_0", "QMD default", rubq["models"]["qwen-q8"], BASELINE, MUTED),
]
out = [
    f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
    f'<rect x="0" y="0" width="{W}" height="10" fill="{ACCENT}"/>',
    text(PAD, 150, "Yuanbao-Reranker-0.6B GGUF", 76, weight=700),
    text(PAD, 206, "Reranker for Russian search in QMD and llama.cpp", 34, MUTED),
    text(PAD, 304, f"RuBQ · {total} RUSSIAN QUESTIONS · RELEVANT PASSAGE RANKED FIRST", 22, FAINT, 600, spacing=1.2),
]
track_x, track_w, y = 560, 400, 376
for label, note, model, color, ink in rows:
    out.append(text(PAD, y + 4, label, 30, ink, 600))
    if note:
        out.append(text(PAD, y + 38, note, 22, FAINT))
    out.append(f'<rect x="{track_x}" y="{y - 14}" width="{track_w}" height="20" rx="10" fill="{TRACK}"/>')
    out.append(f'<rect x="{track_x}" y="{y - 14}" width="{round(model["relevant_top1"] / total * track_w)}" '
               f'height="20" rx="10" fill="{color}"/>')
    out.append(text(W - PAD, y + 10, f'{model["relevant_top1"]} / {total}', 40, ink, 700, "end"))
    y += 96
out.append(text(PAD, H - 44, "Same llama.cpp build · nDCG@10 0.848 vs 0.812 · Apple M4 Pro", 22, FAINT))

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       f'role="img" aria-labelledby="title" font-family="{FONT}">\n'
       f'  <title id="title">Yuanbao-Reranker-0.6B GGUF: relevant passage first for 113 of 150 RuBQ questions, '
       f'102 for Qwen3-Reranker-0.6B Q8_0</title>\n  ' + "\n  ".join(out) + "\n</svg>\n")
(HERE / "social-preview.svg").write_text(svg)
print("ok")
