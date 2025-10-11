# backend/api/main.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, validator

from datetime import datetime
from dateutil import parser as dateparser

from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz

# importa o motor astrológico
from backend.astro_engine.engine_se import compute_chart

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Astro GPT Backend", version="1.0.0")

# ---------------------------------------------------------------------
# Entrada do cliente
# ---------------------------------------------------------------------
class ChartRequestBR(BaseModel):
    nome: str = Field(..., example="Ethiene Herbst")
    sexo: str = Field(..., example="female")
    data: str = Field(..., example="30/07/1987")           # DD/MM/AAAA
    hora: str = Field(..., example="19:05")                # HH:MM (hora local)
    cidade_estado: str = Field(..., example="Mafra-SC")    # "Cidade-UF" ou "Cidade, UF"
    pais: str = Field(..., example="Brasil")

    @validator("sexo")
    def _sexo_norm(cls, v: str) -> str:
        v2 = v.strip().lower()
        if v2 in {"feminino", "fêmea", "mulher", "woman"}:
            return "female"
        if v2 in {"masculino", "macho", "homem", "man"}:
            return "male"
        # aceita "female"/"male"/"unknown"
        if v2 not in {"female", "male", "unknown"}:
            return "unknown"
        return v2


# ---------------------------------------------------------------------
# Utilitários: parse de data/hora, geocodificação e fuso
# ---------------------------------------------------------------------
def _parse_br_datetime(data: str, hora: str) -> datetime:
    """
    Converte "30/07/1987" + "19:05" -> datetime naive (hora local do nascimento).
    """
    try:
        # formatações típicas brasileiras DD/MM/AAAA
        dt = dateparser.parse(f"{data} {hora}", dayfirst=True)
        if not dt:
            raise ValueError("Data/hora inválidas")
        return dt.replace(second=0, microsecond=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Data/hora inválida: {e}")

def _geocode(cidade_estado: str, pais: str) -> Tuple[float, float, str]:
    """
    Usa Nominatim para geocodificar. Retorna (lat, lon, place_str).
    """
    geocoder = Nominatim(user_agent="astro-gpt")
    query = f"{cidade_estado}, {pais}".strip().replace(",,", ",")
    loc = geocoder.geocode(query, language="pt")
    if not loc:
        # tenta uma segunda forma (se veio "Cidade-UF")
        q2 = cidade_estado.replace("-", ", ")
        loc = geocoder.geocode(f"{q2}, {pais}", language="pt")
    if not loc:
        raise HTTPException(status_code=400, detail=f"Cidade não encontrada: '{cidade_estado}, {pais}'")

    place = loc.address
    return (float(loc.latitude), float(loc.longitude), place)

def _tz_offset_hours(dt_local_naive: datetime, lat: float, lon: float) -> float:
    """
    Calcula o offset (em horas) do local na data/hora do nascimento.
    """
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        raise HTTPException(status_code=400, detail="Não foi possível determinar o fuso horário dessa localidade.")
    tz = pytz.timezone(tz_name)
    # localiza como hora local (assumindo que o input é hora local)
    dt_local = tz.localize(dt_local_naive, is_dst=None)
    offset_seconds = dt_local.utcoffset().total_seconds()
    return offset_seconds / 3600.0


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

@app.post(
    "/chart_text_br",
    response_class=PlainTextResponse,
    summary="Retorna o mapa natal em texto (pt-br) usando 6 campos simples."
)
def chart_text_br(req: ChartRequestBR):
    """
    Campos esperados:
    - nome, sexo, data (DD/MM/AAAA), hora (HH:MM, local), cidade_estado (ex.: 'Mafra-SC'), pais (ex.: 'Brasil').
    """
    # 1) Parse data/hora (hora local)
    dt_local = _parse_br_datetime(req.data, req.hora)

    # 2) Geocode (lat/lon + texto do lugar)
    lat, lon, place_str_long = _geocode(req.cidade_estado, req.pais)

    # 3) Offset de fuso (em horas) na data/hora do nascimento
    tz_offset = _tz_offset_hours(dt_local, lat, lon)

    # 4) Monta string final via engine
    try:
        txt = compute_chart(
            year=dt_local.year,
            month=dt_local.month,
            day=dt_local.day,
            hour=dt_local.hour,
            minute=dt_local.minute,
            tz_offset=tz_offset,
            lat=lat,
            lon=lon,
            name=req.nome,
            sex=req.sexo,
            place_str=place_str_long,  # descrição completa retornada pelo geocoder
        )
    except HTTPException:
        raise
    except Exception as e:
        # Loga no console do Uvicorn pra facilitar diagnóstico
        log.exception("Falha ao gerar mapa: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar o mapa: {e}")

    return txt
