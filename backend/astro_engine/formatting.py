# backend/astro_engine/formatting.py

from typing import Dict, List, Any

SIGNS_PT = {
    "Aries": "Aries", "Taurus": "Taurus", "Gemini": "Gemini", "Cancer": "Cancer",
    "Leo": "Leo", "Virgo": "Virgo", "Libra": "Libra", "Scorpio": "Scorpio",
    "Sagittarius": "Sagittarius", "Capricorn": "Capricorn",
    "Aquarius": "Aquarius", "Pisces": "Pisces",
}

def _pad(text: Any, width: int) -> str:
    s = "" if text is None else str(text)
    return s + " " * max(0, width - len(s))

def _get_sidereal_time(header: Dict[str, Any], root: Dict[str, Any]) -> str:
    """
    Busca o tempo sideral em múltiplos nomes/chaves para ser compatível com versões antigas/novas.
    """
    for src in (header, root):
        if not isinstance(src, dict):
            continue
        for key in (
            "sid_time", "sidereal_time", "sidereal_time_str",
            "sidereal", "sidereal_str", "siderealTime", "siderealTimeStr"
        ):
            val = src.get(key)
            if val:
                return str(val)
    return "-"

def _motion_from_row(row: Dict[str, Any]) -> str:
    """
    Decide 'direct' ou 'retrograde' a partir de:
      1) row['motion'] (se vier pronto),
      2) flags retro: row['retro'], row['is_retrograde'], row['rx'], row['R'] etc,
      3) speed < 0
    """
    mot = row.get("motion")
    if isinstance(mot, str) and mot.strip():
        return mot

    # várias flags comuns
    for k in ("retro", "is_retrograde", "rx", "isRx", "R"):
        if k in row:
            v = row.get(k)
            if isinstance(v, bool) and v:
                return "retrograde"
            if isinstance(v, (int, float)) and v != 0:
                return "retrograde"
            if isinstance(v, str) and v.strip().lower() in ("true", "yes", "y", "1", "retro", "retrograde", "r", "rx"):
                return "retrograde"

    # por fim, tenta pelo speed
    sp = row.get("speed")
    try:
        if sp is not None and float(sp) < 0:
            return "retrograde"
    except Exception:
        pass

    return "direct"

def _render_planet_rows(planets: List[Dict[str, Any]], translate_signs: bool = False) -> List[str]:
    lines = []
    lines.append(_pad("planet", 8) + _pad("sign", 11) + _pad("degree", 12) + _pad("motion", 10))
    for p in planets or []:
        planet = p.get("planet", "")
        sign   = p.get("sign", "")
        if translate_signs:
            sign = SIGNS_PT.get(sign, sign)
        degree = p.get("degree", "")
        motion = _motion_from_row(p)
        lines.append(_pad(planet, 8) + _pad(sign, 11) + _pad(degree, 12) + _pad(motion, 10))
    return lines

def _render_house_rows(houses: List[Dict[str, Any]], translate_signs: bool = False) -> List[str]:
    lines = []
    lines.append("House positions (Placidus)")
    for h in houses or []:
        nm = h.get("house", "")
        sign = h.get("sign", "")
        if translate_signs:
            sign = SIGNS_PT.get(sign, sign)
        deg = h.get("degree", "")
        lines.append(_pad(nm, 14) + _pad(sign, 11) + _pad(deg, 8))
    return lines

def _render_header(root: Dict[str, Any], translate_signs: bool = False) -> List[str]:
    header: Dict[str, Any] = root.get("header", {}) if isinstance(root.get("header"), dict) else {}
    place_str = header.get("place_str") or root.get("place_str") or ""
    ut_str    = header.get("ut_str")    or root.get("ut_str")    or ""
    coords    = header.get("coords_str") or root.get("coords_str") or ""
    sid_time  = _get_sidereal_time(header, root)

    lines = []
    lines.append("Astrological Data used for Personal Portrait Short Horoscope")
    # (mantenha/ajuste o título conforme seu fluxo)
    lines.append("for Ethiene Herbst (female)")
    if place_str or ut_str:
        lines.append(f"in {place_str}\tU.T.:\t{ut_str}")
    if coords or sid_time:
        lines.append(f"{coords}\tsid. time:\t{sid_time}")
    lines.append("")
    return lines

def build_text_output(payload: Dict[str, Any]) -> str:
    """
    Versão 'geral' (EN).
    """
    out: List[str] = []
    out.extend(_render_header(payload, translate_signs=False))
    out.append("Planetary positions")
    out.extend(_render_planet_rows(payload.get("planets", []), translate_signs=False))
    out.append("")
    out.extend(_render_house_rows(payload.get("houses", []), translate_signs=False))
    out.append("")
    aspects = payload.get("aspects") or []
    if aspects:
        out.append("Major aspects")
        for asp in aspects:
            out.append(f"{asp.get('p1','')} {asp.get('type','')} {asp.get('p2','')} {asp.get('orb','')}")
        out.append("")
    return "\n".join(out) + "\n"

def build_text_output_br(payload: Dict[str, Any]) -> str:
    """
    Versão usada pelo endpoint BR (/chart_text_br). 
    Aplica as mesmas correções de sid. time e motion.
    """
    out: List[str] = []
    out.extend(_render_header(payload, translate_signs=True))
    out.append("Planetary positions")
    out.extend(_render_planet_rows(payload.get("planets", []), translate_signs=True))
    out.append("")
    out.extend(_render_house_rows(payload.get("houses", []), translate_signs=True))
    out.append("")
    aspects = payload.get("aspects") or []
    if aspects:
        out.append("Major aspects")
        for asp in aspects:
            out.append(f"{asp.get('p1','')} {asp.get('type','')} {asp.get('p2','')} {asp.get('orb','')}")
        out.append("")
    return "\n".join(out) + "\n"
