"""Fake renderer implementations to simulate dockerized renderers for PoC.

These produce neutral SVG outputs (no styles/colors) for testing the end-to-end flow.
"""
from __future__ import annotations

from typing import Tuple
import xml.etree.ElementTree as ET


def _svg_with_text(body: str) -> str:
    # Minimal neutral SVG without style tags or colors
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", version="1.1")
    g = ET.SubElement(root, "g")
    text = ET.SubElement(g, "text", x="10", y="20")
    text.text = body[:1000]
    return ET.tostring(root, encoding="unicode")


def render_mermaid(input_text: str) -> Tuple[bool, str]:
    """Render a simple Mermaid `sequenceDiagram` into an SVG.

    This is a lightweight renderer for POC/testing only. It supports basic
    participant declarations and arrow lines like `A->>B: msg` or `A-->>B: r`.
    If the input is not a `sequenceDiagram`, falls back to text embed.
    """
    lines = [l.strip() for l in (input_text or "").splitlines() if l.strip()]
    if not lines:
        return True, _svg_with_text("Mermaid: (empty)")

    if not lines[0].lower().startswith("sequencediagram") and "sequenceDiagram" not in lines[0]:
        return True, _svg_with_text("Mermaid:\n" + input_text)

    # parse simple sequence lines
    events = []
    participants = []
    for l in lines[1:]:
        # support ->, ->>, -->> and <-- variants
        if "->>" in l or "->" in l or "-->>" in l or "--" in l or "<-" in l or "<<-" in l:
            # split at ':' for message label
            parts = l.split(":", 1)
            arrow_part = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 else ""
            # find source and target
            for sep in ("->>", "-->>", "->", "--", "<-", "<<-"):
                if sep in arrow_part:
                    src, tgt = [p.strip() for p in arrow_part.split(sep, 1)]
                    break
            else:
                continue
            # normalize direction for left->right drawing
            forward = not (sep in ("<-", "<<-"))
            if not forward:
                # swap
                src, tgt = tgt, src
            if src not in participants:
                participants.append(src)
            if tgt not in participants:
                participants.append(tgt)
            events.append({"src": src, "tgt": tgt, "label": label})
        else:
            # treat as participant declaration 'participant A as X' or 'Alice:"
            if l.lower().startswith("participant"):
                tok = l.split(None, 1)[1].strip()
                name = tok.split(" ", 1)[0]
                if name not in participants:
                    participants.append(name)

    # layout constants
    width = 600
    p_count = max(1, len(participants))
    margin = 40
    step_x = (width - 2 * margin) / max(1, p_count - 1) if p_count > 1 else 0
    header_h = 30
    lifeline_y0 = header_h + 10
    lifeline_h = 300
    event_spacing = 40

    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", version="1.1", width=str(width), height=str(lifeline_h + 80))
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(defs, "marker", id="arrow", markerWidth="10", markerHeight="7", refX="10", refY="3.5", orient="auto")
    ET.SubElement(marker, "path", d="M0,0 L10,3.5 L0,7 z", fill="#222")

    # draw participants
    xs = {}
    for i, p in enumerate(participants):
        x = margin + i * step_x if p_count > 1 else width // 2
        xs[p] = x
        # participant box
        ET.SubElement(svg, "rect", x=str(x - 30), y=str(5), width="60", height="24", fill="#ffffff", stroke="#222", rx="6")
        t = ET.SubElement(svg, "text", x=str(x), y="22", fill="#000", style="font-family:Arial; font-size:12px;", **{"text-anchor": "middle"})
        t.text = p
        # lifeline (dashed)
        line = ET.SubElement(svg, "line", x1=str(x), y1=str(lifeline_y0), x2=str(x), y2=str(lifeline_y0 + lifeline_h), stroke="#666", **{"stroke-dasharray": "4 4"})

    # draw events
    ey = lifeline_y0 + 10
    for ev in events:
        sx = xs.get(ev["src"], margin)
        tx = xs.get(ev["tgt"], margin + 100)
        # arrow line
        line = ET.SubElement(svg, "line", x1=str(sx), y1=str(ey), x2=str(tx), y2=str(ey), stroke="#222", **{"stroke-width": "2", "marker-end": "url(#arrow)"})
        # label
        if ev.get("label"):
            midx = (sx + tx) / 2
            tl = ET.SubElement(svg, "text", x=str(midx), y=str(ey - 6), fill="#000", style="font-family:Arial; font-size:11px;", **{"text-anchor": "middle"})
            tl.text = ev["label"]
        ey += event_spacing

    return True, ET.tostring(svg, encoding="unicode")


def render_structurizr(input_text: str) -> Tuple[bool, str]:
    svg = _svg_with_text("Structurizr:\n" + input_text)
    return True, svg


def render_plantuml(input_text: str) -> Tuple[bool, str]:
    svg = _svg_with_text("PlantUML:\n" + input_text)
    return True, svg
