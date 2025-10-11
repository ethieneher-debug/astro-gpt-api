# backend/astro_engine/aspects.py
from typing import List, Dict

ASPECT_LABELS_PT = {
    "Conjunction": "Conjunção",
    "Sextile": "Sextil",
    "Square": "Quadratura",
    "Trine": "Trígono",
    "Quincunx": "Quincúncio",
    "Opposition": "Oposição",
}

def summarize_major_aspects(aspects: List[Dict]) -> List[str]:
    lines = []
    for a in aspects:
        if a["type"] in ASPECT_LABELS_PT:
            lines.append(f"{a['p1']} {a['type']} {a['p2']} {a['orb']}°")
    return lines
