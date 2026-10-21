from __future__ import annotations

from html import escape
from pathlib import Path

from .recorder import read_jsonl


def _chart(rows, title, value, color, ceiling=None):
    samples = [(r["relative_time_seconds"], value(r)) for r in rows]
    values = [v for _, v in samples if v is not None]
    upper = ceiling or max(1, max(values, default=1)*1.1)
    duration = max(1, samples[-1][0]) if samples else 1
    points = " ".join(f"{45+710*t/duration:.2f},{150-120*max(0,min(upper,v))/upper:.2f}" for t, v in samples if v is not None)
    return f'<h4>{escape(title)}</h4><svg viewBox="0 0 800 180" role="img" aria-label="{escape(title)}"><path d="M45 20V150H760" fill="none" stroke="#888"/><polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/><text x="45" y="175">0 s</text><text x="700" y="175">{duration:.1f} s</text><text x="2" y="25">{upper:.1f}</text></svg>'


def write_review(directory: Path):
    panels = []
    for branch in ("R", "CF"):
        frames_path = directory/branch/"frames.jsonl"
        if not frames_path.exists():
            continue
        rows = read_jsonl(frames_path)
        content = f'<section><h2>{branch}</h2><video controls preload="metadata" src="{branch}/episode.mp4"></video>'
        content += _chart(rows, "Ego speed (km/h)", lambda r:r["ego"]["speed_mps"]*3.6, "#1265ab")
        content += _chart(rows, "Primary actor speed (km/h)", lambda r:r["actors"][0]["speed_mps"]*3.6, "#6941a5")
        content += _chart(rows, "Bumper clearance (m)", lambda r:r["risk"]["bumper_gap_m"], "#a35b00")
        content += _chart(rows, "Time headway (s, clipped at 5)", lambda r:r["risk"]["time_headway_seconds"] if r["risk"]["corridor_overlap"] else None, "#267c42", 5)
        if any("lateral_clearance_m" in r["risk"] for r in rows):
            content += _chart(rows, "Lateral body clearance (m)", lambda r:r["risk"].get("lateral_clearance_m"), "#a35b00")
            content += '<p>Xe ép ngang có thể nằm ngoài camera nhìn trước; cần đối chiếu footprint, vị trí và boxes_2d, không suy ra visibility từ nhãn risk.</p>'
        content += _chart(rows, "Closing TTC (s, clipped at 10)", lambda r:r["risk"]["ttc_seconds"], "#6941a5", 10)
        content += _chart(rows, "Risk label (0/1)", lambda r:int(r["risk"]["is_risk"]), "#bd2626", 1)
        panels.append(content+"</section>")
    html = '<!doctype html><html lang="vi"><meta charset="utf-8"><title>R–CF pair review</title><style>body{font:16px system-ui;margin:24px;background:#f4f6f8}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}section{background:white;padding:20px}video,svg{width:100%}h4{margin-bottom:0}@media(max-width:800px){main{grid-template-columns:1fr}}</style><h1>R–CF pair review</h1><p>Đối chiếu validation.json với video và các đại lượng đo được. Khoảng hở là khoảng cách dọc giữa footprint; headway chỉ vẽ khi cùng hành lang.</p><main>'+"".join(panels)+"</main></html>"
    (directory/"review.html").write_text(html, encoding="utf-8")
