# backend/astro_engine/engine_se.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import swisseph as swe


# -----------------------------------------------------------------------------
# Configuração da Swiss Ephemeris (pasta .../astro-gpt/ephe)
# -----------------------------------------------------------------------------
EPHE_PATH = str(Path(__file__).resolve().parents[2] / "ephe")
swe.set_ephe_path(EPHE_PATH)


# -----------------------------------------------------------------------------
# Helpers para compatibilidade entre builds do pyswisseph
# -----------------------------------------------------------------------------
def _swe_const(name_se: str, name_plain: str, fallback: int) -> int:
    """
    Tenta ler a constante do swe com o nome 'SE_*' (builds modernas),
    caso não exista tenta sem o 'SE_' (builds antigas), e por fim usa um fallback.
    """
    return getattr(swe, name_se, getattr(swe, name_plain, fallback))


# Flags de cálculo (robusto a diferenças entre builds do pyswisseph)
_SWIEPH   = getattr(swe, "SEFLG_SWIEPH", 0)
_TRUEPOS  = getattr(swe, "SEFLG_TRUEPOS", getattr(swe, "SEFLG_TRUEPOSITION", 0))
SEFLAGS   = _SWIEPH | _TRUEPOS


# -----------------------------------------------------------------------------
# Utilitários de ângulo, formatação e diferenças com "wrap"
# -----------------------------------------------------------------------------
SIGNS = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
)

# Constantes planetárias compatíveis com qualquer build
PLANETS: List[Tuple[int, str]] = [
    (_swe_const("SE_SUN",       "SUN",       0),  "Sun"),
    (_swe_const("SE_MOON",      "MOON",      1),  "Moon"),
    (_swe_const("SE_MERCURY",   "MERCURY",   2),  "Mercury"),
    (_swe_const("SE_VENUS",     "VENUS",     3),  "Venus"),
    (_swe_const("SE_MARS",      "MARS",      4),  "Mars"),
    (_swe_const("SE_JUPITER",   "JUPITER",   5),  "Jupiter"),
    (_swe_const("SE_SATURN",    "SATURN",    6),  "Saturn"),
    (_swe_const("SE_URANUS",    "URANUS",    7),  "Uranus"),
    (_swe_const("SE_NEPTUNE",   "NEPTUNE",   8),  "Neptune"),
    (_swe_const("SE_PLUTO",     "PLUTO",     9),  "Pluto"),
    (
        _swe_const(
            "SE_TRUE_NODE",
            "TRUE_NODE",
            _swe_const("SE_MEAN_NODE", "MEAN_NODE", 11)
        ),
        "True Node"
    ),
]

MAJOR_ASPECTS = {
    "Conjunction": 0.0,
    "Opposition": 180.0,
    "Trine": 120.0,
    "Square": 90.0,
    "Sextile": 60.0,
    "Quincunx": 150.0,
}

# orbes (em graus) por aspecto
ASPECT_ORBS = {
    "Conjunction": 8.0,
    "Opposition": 8.0,
    "Trine": 7.0,
    "Square": 6.0,
    "Sextile": 4.0,
    "Quincunx": 3.0,
}


def _wrap360(a: float) -> float:
    return a % 360.0


def _shortest_signed_diff(a: float, b: float) -> float:
    """Diferença angular assinada (a - b) em (-180, +180]."""
    return ((a - b + 180.0) % 360.0) - 180.0


def _deg_to_dms_str(deg: float) -> str:
    """
    Converte 123.456… -> '123°27'22'
    (sem segundos decimais para seguir o visual do cliente).
    """
    d = int(math.floor(deg))
    m_float = (deg - d) * 60.0
    m = int(math.floor(m_float))
    s = int(round((m_float - m) * 60.0))
    # Ajustes de arredondamento para evitar 60"
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    return f"{d}°{m:02d}'{s:02d}"


def _sign_of(lon: float) -> str:
    return SIGNS[int(_wrap360(lon) // 30)]


# -----------------------------------------------------------------------------
# Tempo e data juliana
# -----------------------------------------------------------------------------
def _to_julday_utc(
    y: int, m: int, d: int, hour: int, minute: int, tz_offset_hours: float
) -> Tuple[float, float]:
    """
    Converte hora local + fuso para JD UT.
    Retorna (jd_ut, ut_decimal_hours).
    """
    # hora local -> UTC
    ut_hours = hour + minute / 60.0 - tz_offset_hours
    jd_ut = swe.julday(y, m, d, ut_hours)
    return jd_ut, ut_hours


# -----------------------------------------------------------------------------
# Retrógrado robusto (derivada central com wrap)
# -----------------------------------------------------------------------------
_STEP_HOURS = 12.0         # janela grande para planetas lentos
_STEP_DAYS  = _STEP_HOURS / 24.0
_EPS_DEG    = 1e-4          # 0.0001° ~ 0.36 arcsec

def _motion_sign(jd_ut: float, ipl: int) -> float:
    """
    Variação angular assinada entre t+step e t-step usando wrap.
    > 0 => prógrado; < 0 => retrógrado; ~0 => estacionário.
    """
    lon_m = swe.calc_ut(jd_ut - _STEP_DAYS, ipl, SEFLAGS)[0][0] % 360.0
    lon_p = swe.calc_ut(jd_ut + _STEP_DAYS, ipl, SEFLAGS)[0][0] % 360.0
    return _shortest_signed_diff(lon_p, lon_m)

def _is_retrograde(jd_ut: float, ipl: int) -> str:
    """
    Classificação a partir do sinal. Limiar pequeno para não mascarar
    planetas lentos (Saturno/Urano/Netuno/Plutão).
    """
    s = _motion_sign(jd_ut, ipl)
    if s > _EPS_DEG:
        return "direct"
    elif s < -_EPS_DEG:
        return "retrograde"
    else:
        return "stationary"
        # Se preferir tratar estacionário como retrógrado:
        # return "retrograde"


# -----------------------------------------------------------------------------
# Cálculo de posições e casas
# -----------------------------------------------------------------------------
def _compute_planets(jd_ut: float, lat: float, lon: float) -> Dict[str, Dict[str, object]]:
    """
    Calcula longitudes e casas Placidus + status de movimento para cada planeta.
    Retorna dict: { "Sun": {lon, sign, house, motion, degree_str}, ... }
    """
    # --- houses_ex com normalização do retorno (2 ou 3 itens) ---
    houses_res = swe.houses_ex(jd_ut, lat, lon, b'P')
    if not isinstance(houses_res, (list, tuple)):
        raise ValueError("swe.houses_ex retornou um tipo inesperado.")

    if len(houses_res) == 3:
        cusps, ascmc, _ = houses_res
    elif len(houses_res) == 2:
        cusps, ascmc = houses_res
    else:
        # Tenta heurística genérica
        cusps = houses_res[0]
        ascmc = houses_res[1] if len(houses_res) > 1 else [0.0] * 10

    planet_data: Dict[str, Dict[str, object]] = {}

    # Encontrar casa de uma longitude
    def house_of(l: float) -> int:
        x = _wrap360(l)
        # Percorre 12 casas verificando em qual intervalo [cusp_i, cusp_{i+1}) cai
        for i in range(12):
            c1 = cusps[i] % 360.0
            c2 = cusps[(i + 1) % 12] % 360.0
            if c1 <= c2:
                inside = (x >= c1) and (x < c2)
            else:
                # intervalo cruzando 0°
                inside = (x >= c1) or (x < c2)
            if inside:
                return i + 1
        return 12  # fallback

    for ipl, name in PLANETS:
        lon_deg = swe.calc_ut(jd_ut, ipl, SEFLAGS)[0][0] % 360.0
        sign = _sign_of(lon_deg)
        house = house_of(lon_deg)
        motion = _is_retrograde(jd_ut, ipl)

        planet_data[name] = {
            "lon": lon_deg,
            "sign": sign,
            "house": house,
            "motion": motion,
            "degree_str": _deg_to_dms_str(lon_deg),
        }

    # Também guardamos rapidamente ASC/MC
    asc_lon = ascmc[0] % 360.0
    mc_lon  = ascmc[1] % 360.0
    planet_data["_ASC"] = {
        "lon": asc_lon,
        "sign": _sign_of(asc_lon),
        "degree_str": _deg_to_dms_str(asc_lon),
    }
    planet_data["_MC"] = {
        "lon": mc_lon,
        "sign": _sign_of(mc_lon),
        "degree_str": _deg_to_dms_str(mc_lon),
    }

    # Guardamos as cúspides das casas também
    planet_data["_HOUSES"] = {
        i + 1: {
            "lon": cusps[i] % 360.0,
            "sign": _sign_of(cusps[i] % 360.0),
            "degree_str": _deg_to_dms_str(cusps[i] % 360.0),
        }
        for i in range(12)
    }

    return planet_data


def _find_major_aspects(planet_data: Dict[str, Dict[str, object]]) -> List[Tuple[str, str, str, float]]:
    """
    Encontra aspectos maiores entre planetas.
    Retorna lista de tuplas: (BodyA, AspectName, BodyB, orb_abs_em_graus)
    """
    aspects: List[Tuple[str, str, str, float]] = []
    names = [n for _, n in PLANETS]

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            lon_a = float(planet_data[a]["lon"])
            lon_b = float(planet_data[b]["lon"])

            diff = abs(_shortest_signed_diff(lon_a, lon_b))  # [0..180]
            for asp_name, asp_angle in MAJOR_ASPECTS.items():
                orb = abs(diff - asp_angle)
                max_orb = ASPECT_ORBS[asp_name]
                if orb <= max_orb:
                    aspects.append((a, asp_name, b, round(orb, 2)))
    return aspects


# -----------------------------------------------------------------------------
# Formatação (tabela texto no estilo solicitado)
# -----------------------------------------------------------------------------
def _fmt_header(
    name: str,
    sex: str,
    date_str: str,
    local_time_str: str,
    place_str: str,
    ut_str: str,
    sidereal_time_str: str,
) -> str:
    lines = [
        "Astrological Data used for Personal Portrait Short Horoscope",
        f"for {name} ({sex})",
        f"born on {date_str}\tlocal time:\t{local_time_str}\tU.T.:\t{ut_str}",
        f"in {place_str}\tsid. time:\t{sidereal_time_str}",
        "",
    ]
    return "\n".join(lines)


def _fmt_planets(planet_data: Dict[str, Dict[str, object]]) -> str:
    header = [
        "Planetary positions",
        "planet\tsign\tdegree\t\tmotion",
    ]
    rows = []
    for _, name in PLANETS:
        p = planet_data[name]
        rows.append(
            f"{name}\t{p['sign']}\t{p['degree_str']}\tin house {p['house']}\t{p['motion']}"
        )

    rows.append("Planets at the end of a house are interpreted in the next house.")
    return "\n".join(header + rows)


def _fmt_houses(planet_data: Dict[str, Dict[str, object]]) -> str:
    h = planet_data["_HOUSES"]
    asc = planet_data["_ASC"]
    mc  = planet_data["_MC"]
    lines = [
        "",
        "House positions (Placidus)",
        f"Ascendant\t{asc['sign']}\t{asc['degree_str']}",
        f"2nd House\t{h[2]['sign']}\t{h[2]['degree_str']}",
        f"3rd House\t{h[3]['sign']}\t{h[3]['degree_str']}",
        f"Imum Coeli\t{mc['sign']}\t{mc['degree_str']}",
        f"5th House\t{h[5]['sign']}\t{h[5]['degree_str']}",
        f"6th House\t{h[6]['sign']}\t{h[6]['degree_str']}",
        f"Descendant\t{SIGNS[(SIGNS.index(asc['sign'])+6)%12]}\t{h[7]['degree_str']}",
        f"8th House\t{h[8]['sign']}\t{h[8]['degree_str']}",
        f"9th House\t{h[9]['sign']}\t{h[9]['degree_str']}",
        f"Medium Coeli\t{mc['sign']}\t{mc['degree_str']}",
        f"11th House\t{h[11]['sign']}\t{h[11]['degree_str']}",
        f"12th House\t{h[12]['sign']}\t{h[12]['degree_str']}",
    ]
    return "\n".join(lines)


def _fmt_aspects(aspects: List[Tuple[str, str, str, float]]) -> str:
    if not aspects:
        return ""
    lines = ["", "Major aspects"]
    for a, asp, b, orb in aspects:
        lines.append(f"{a}\t{asp}\t{b}\t{orb:.2f}°")
    lines.append("Numbers indicate orb (deviation from the exact aspect angle).")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# API principal usada pelo endpoint
# -----------------------------------------------------------------------------
def compute_chart(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    tz_offset: float,
    lat: float,
    lon: float,
    name: str = "Unknown",
    sex: str = "unknown",
    place_str: str = "",
) -> str:
    """
    Retorna o texto do mapa no formato pedido (em inglês, estilo do cliente).
    year,month,day,hour,minute -> hora LOCAL; tz_offset em horas; lat,lon em graus decimais.
    """
    # JD UT e hora UT (decimal)
    jd_ut, ut_hours = _to_julday_utc(year, month, day, hour, minute, tz_offset)

    # Strings de data/hora
    local_time_str = f"{hour:02d}:{minute:02d}"
    ut_h = int(math.floor(ut_hours))
    ut_m = int(round((ut_hours - ut_h) * 60.0))
    if ut_m == 60:
        ut_m = 0
        ut_h += 1
    ut_str = f"{ut_h:02d}:{ut_m:02d}"
    date_str = f"{day:02d} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} {year}"

    # Tempo sideral (para exibir; o cálculo das casas já usa internamente)
    sid = swe.sidtime(jd_ut)
    sid_hours = int(math.floor(sid))
    sid_minutes = int(math.floor((sid - sid_hours) * 60.0))
    sid_seconds = int(round((((sid - sid_hours) * 60.0) - sid_minutes) * 60.0))
    if sid_seconds == 60:
        sid_seconds = 0
        sid_minutes += 1
    if sid_minutes == 60:
        sid_minutes = 0
        sid_hours = (sid_hours + 1) % 24
    sidereal_time_str = f"{sid_hours:02d}:{sid_minutes:02d}:{sid_seconds:02d}"

    # Cálculos astrológicos
    planets = _compute_planets(jd_ut, lat, lon)
    aspects = _find_major_aspects(planets)

    # Montagem do texto final
    header = _fmt_header(
        name=name,
        sex=sex,
        date_str=date_str,
        local_time_str=local_time_str,
        place_str=place_str if place_str else f"{lat:.4f}, {lon:.4f}",
        ut_str=ut_str,
        sidereal_time_str=sidereal_time_str,
    )
    body = _fmt_planets(planets)
    houses = _fmt_houses(planets)
    aspects_txt = _fmt_aspects(aspects)

    text = "\n".join([header, body, houses, aspects_txt]).strip() + "\n"
    return text
