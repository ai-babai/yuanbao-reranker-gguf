#!/usr/bin/env python3
"""Write the English and Russian header SVGs from figure-data.json.

Render each SVG to PNG at 2x with headless Chrome, for example:
  chrome --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --default-background-color=00000000 --window-size=1000,<height> \
    --screenshot=assets/yuanbao-reranker-header-en.png assets/header/header-en.svg
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "figure-data.json").read_text())

W = 1000
PAD = 52
INK, MUTED, FAINT = "#141413", "#55544f", "#6b6a65"
SURFACE, BORDER, TRACK, RULE = "#fcfcfb", "#dddcd6", "#ebeae5", "#e6e5e0"
ACCENT, BASELINE = "#2a78d6", "#8f8e88"
FONT = "-apple-system, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"

TEXT = {
    "en": {
        "subtitle": "Multilingual reranker for llama.cpp and QMD",
        "files": "Q8_0 · Q4_K_M · F16",
        "example": "RUSSIAN EXAMPLE · ONE QUESTION, TWO PASSAGES · Q8_0 · /v1/rerank",
        "gloss": ["Open the subscriptions section and turn off automatic renewal.",
                  "To change the password, open the security settings."],
        "rubq": "OUR RUSSIAN CHECK · RuBQ, 150 QUESTIONS · SAME LLAMA.CPP BUILD",
        "of": "of",
        "first": "relevant passage ranked first",
        "qwen": "Qwen3-Reranker-0.6B Q8_0 · QMD default",
        "footer": "Apple M4 Pro · llama.cpp 5fddd0b · nDCG@10 gain +0.036, 95% CI +0.018 to +0.054",
        "decimal": ".",
    },
    "ru": {
        "subtitle": "Многоязычный реранкер для llama.cpp и QMD",
        "files": "Q8_0 · Q4_K_M · F16",
        "example": "ПРИМЕР НА РУССКОМ · ОДИН ВОПРОС, ДВА ФРАГМЕНТА · Q8_0 · /v1/rerank",
        "gloss": None,
        "rubq": "НАША ПРОВЕРКА НА РУССКОМ · RuBQ, 150 ВОПРОСОВ · ОДНА СБОРКА LLAMA.CPP",
        "of": "из",
        "first": "релевантный фрагмент первым",
        "qwen": "Qwen3-Reranker-0.6B Q8_0 · штатный в QMD",
        "footer": "Apple M4 Pro · llama.cpp 5fddd0b · прирост nDCG@10 +0,036, 95% ДИ от +0,018 до +0,054",
        "decimal": ",",
    },
}


def number(value, digits, lang):
    return f"{value:.{digits}f}".replace(".", TEXT[lang]["decimal"])


def text(x, y, content, size, color=INK, weight=400, anchor="start", spacing=0):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}"{extra}>{escape(content)}</text>')


def build(lang):
    t = TEXT[lang]
    example = DATA["rerank_example"]
    rubq = DATA["rubq"]
    out = []
    y = 84
    out.append(text(PAD, y, "Yuanbao-Reranker-0.6B GGUF", 44, weight=700))
    out.append(text(W - PAD, y, t["files"], 20, FAINT, 600, "end"))
    y += 40
    out.append(text(PAD, y, t["subtitle"], 24, MUTED))
    y += 60
    out.append(text(PAD, y, t["example"], 17, FAINT, 600, spacing=1))
    y += 42
    out.append(text(PAD, y, f"«{example['query']}»", 28, weight=600))
    track_x, track_w = PAD + 48, 700
    for rank, row in enumerate(example["results"], start=1):
        first = rank == 1
        y += 50
        out.append(f'<circle cx="{PAD + 16}" cy="{y - 8}" r="16" fill="{ACCENT if first else TRACK}"/>')
        out.append(text(PAD + 16, y - 1, str(rank), 18, "#ffffff" if first else MUTED, 700, "middle"))
        out.append(text(track_x, y, row["document"], 24, INK if first else MUTED, 500 if first else 400))
        if t["gloss"]:
            y += 26
            out.append(text(track_x, y, t["gloss"][rank - 1], 19, FAINT))
        y += 22
        fill = max(4, round(row["relevance_score"] * track_w))
        out.append(f'<rect x="{track_x}" y="{y}" width="{track_w}" height="12" rx="6" fill="{TRACK}"/>')
        out.append(f'<rect x="{track_x}" y="{y}" width="{fill}" height="12" rx="{min(6, fill / 2)}" fill="{ACCENT}"/>')
        digits = 3 if row["relevance_score"] >= 0.01 else 4
        out.append(text(W - PAD, y + 13, number(row["relevance_score"], digits, lang), 28,
                        INK if first else MUTED, 700, "end"))
        y += 12
    y += 40
    out.append(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" stroke="{RULE}" stroke-width="2"/>')
    y += 40
    out.append(text(PAD, y, t["rubq"], 17, FAINT, 600, spacing=1))
    columns = [
        (PAD, ACCENT, "Yuanbao-Reranker-0.6B Q8_0", rubq["models"]["yuanbao-q8"], INK),
        (W // 2 - 6, BASELINE, t["qwen"], rubq["models"]["qwen-q8"], MUTED),
    ]
    top = y
    for x, color, label, model, ink in columns:
        y = top + 40
        out.append(f'<rect x="{x}" y="{y - 13}" width="14" height="14" rx="3" fill="{color}"/>')
        out.append(text(x + 24, y, label, 19, ink, 600))
        y += 58
        out.append(f'<text x="{x}" y="{y}" fill="{ink}" font-weight="700">'
                   f'<tspan font-size="54">{model["relevant_top1"]}</tspan>'
                   f'<tspan font-size="26" dx="10" fill="{MUTED}" font-weight="600">{t["of"]} {rubq["queries"]}</tspan></text>')
        y += 34
        out.append(text(x, y, t["first"], 20, MUTED))
        y += 28
        out.append(text(x, y, f'nDCG@10 {number(model["ndcg_at_10"], 3, lang)}', 20, MUTED))
    y += 52
    out.append(text(PAD, y, t["footer"], 17, FAINT))
    height = y + 36
    body = "\n  ".join(out)
    title = f"Yuanbao-Reranker-0.6B GGUF — {t['subtitle']}"
    return height, (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" '
        f'role="img" aria-labelledby="title" font-family="{FONT}">\n'
        f'  <title id="title">{escape(title)}</title>\n'
        f'  <rect x="1" y="1" width="{W - 2}" height="{height - 2}" rx="28" fill="{SURFACE}" stroke="{BORDER}" stroke-width="2"/>\n'
        f'  {body}\n</svg>\n'
    )


if __name__ == "__main__":
    for lang in TEXT:
        height, svg = build(lang)
        (HERE / f"header-{lang}.svg").write_text(svg)
        print(lang, height)
