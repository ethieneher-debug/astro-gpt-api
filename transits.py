from datetime import date
import swisseph as swe
from typing import List, Dict
from fastapi import FastAPI
from pydantic import BaseModel

# Inicializa o app FastAPI
app = FastAPI()

# Inicializa o caminho para as efemérides
swe.set_ephe_path("./ephe")  # ajuste conforme sua estrutura

# Mapeia nomes de planetas para os códigos do pyswisseph
PLANETAS = {
    "Sol": swe.SUN,
    "Lua": swe.MOON,
    "Mercurio": swe.MERCURY,
    "Venus": swe.VENUS,
    "Marte": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturno": swe.SATURN,
    "Urano": swe.URANUS,
    "Netuno": swe.NEPTUNE,
    "Plutao": swe.PLUTO,
}

# Ângulos dos aspectos principais
ASPECTOS = {
    "conjuncao": 0,
    "oposicao": 180,
    "trigono": 120,
    "quadratura": 90,
    "sextil": 60
}

def calcular_transitos(
    planeta_transito: str,
    planeta_natal: str,
    longitude_natal: float,
    aspecto: str,
    orbe: float = 1.5,
    ano: int = 2026
) -> List[Dict]:
    """
    Retorna uma lista de datas em que o planeta em trânsito faz aspecto com o planeta natal
    """
    resultados = []

    jd_inicio = swe.julday(ano, 1, 1)
    jd_fim = swe.julday(ano, 12, 31)

    planeta_trans = PLANETAS[planeta_transito]
    angulo_aspecto = ASPECTOS[aspecto]

    dia = 0
    while jd_inicio + dia <= jd_fim:
        jd = jd_inicio + dia
        pos, _ = swe.calc_ut(jd, planeta_trans)
        long_transito = pos[0] % 360

        distancia = abs((long_transito - longitude_natal + 180) % 360 - 180)

        if abs(distancia - angulo_aspecto) <= orbe:
            data = swe.revjul(jd)
            resultados.append({
                "data": date(*map(int, data[:3])).isoformat(),
                "grau_transito": round(long_transito, 2),
                "grau_natal": round(longitude_natal, 2),
                "diferenca": round(distancia, 2)
            })

        dia += 1

    return resultados

# Modelo para receber requisições via POST
class TransitoRequest(BaseModel):
    planeta_transito: str
    planeta_natal: str
    longitude_natal: float
    aspecto: str
    orbe: float = 1.5
    ano: int = 2026

# Endpoint da API
@app.post("/transitos")
def obter_transitos(req: TransitoRequest):
    return calcular_transitos(
        planeta_transito=req.planeta_transito,
        planeta_natal=req.planeta_natal,
        longitude_natal=req.longitude_natal,
        aspecto=req.aspecto,
        orbe=req.orbe,
        ano=req.ano
    )
