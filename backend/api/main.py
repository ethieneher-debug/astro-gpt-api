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
    data: str = Field(..., example="30/07/1987")
    hora: str = Field(..., example="19:05")
    cidade_estado: str = Field(..., example="Mafra-SC")
    pais: str = Field(..., example="Brasil")

    @validator("sexo")
    def _sexo_norm(cls, v: str) -> str:
        v2 = v.strip().lower()
        if v2 in {"feminino", "fêmea", "mulher", "woman"}:
            return "female"
        if v2 in {"masculino", "macho", "homem", "man"}:
            return "male"
        if v2 not in {"female", "male", "unknown"}:
            return "unknown"
        return v2

# ---------------------------------------------------------------------
# Utilitários: parse de data/hora, geocodificação e fuso
# ---------------------------------------------------------------------
def _parse_br_datetime(data: str, hora: str) -> datetime:
    try:
        dt = dateparser.parse(f"{data} {hora}", dayfirst=True)
        if not dt:
            raise ValueError("Data/hora inválidas")
        return dt.replace(second=0, microsecond=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Data/hora inválida: {e}")

def _geocode(cidade_estado: str, pais: str) -> Tuple[float, float, str]:
    geocoder = Nominatim(user_agent="astro-gpt-prod", timeout=10)
    query = f"{cidade_estado}, {pais}".strip().replace(",,", ",")
    loc = geocoder.geocode(query, language="pt")
    if not loc:
        # tenta segunda forma: "Cidade-UF" → "Cidade, UF"
        q2 = cidade_estado.replace("-", ", ")
        loc = geocoder.geocode(f"{q2}, {pais}", language="pt")
    if not loc:
        raise HTTPException(status_code=400, detail=f"Cidade não encontrada: '{cidade_estado}, {pais}'")
    return float(loc.latitude), float(loc.longitude), loc.address

def _tz_offset_hours(dt_local_naive: datetime, lat: float, lon: float) -> float:
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        raise HTTPException(status_code=400, detail="Fuso horário não encontrado para essa localização.")
    tz = pytz.timezone(tz_name)
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
    dt_local = _parse_br_datetime(req.data, req.hora)
    lat, lon, place_str_long = _geocode(req.cidade_estado, req.pais)
    tz_offset = _tz_offset_hours(dt_local, lat, lon)

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
            place_str=place_str_long,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Falha ao gerar mapa: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar o mapa: {e}")

    return txt
