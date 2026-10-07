"""Ayudantes para los formularios de características de vivienda."""
from __future__ import annotations

from .ml.constants import BOOLEANAS

CAMPOS_TEXTO = [
    "tipo", "distrito", "area_terreno", "area_construida", "habitaciones", "banos",
    "pisos", "antiguedad", "estado_conservacion", "acabados", "cochera",
]


def valores_por_defecto() -> dict:
    v = {
        "tipo": "Departamento", "distrito": "Cayma", "area_terreno": "", "area_construida": "100",
        "habitaciones": "3", "banos": "2", "pisos": "1", "antiguedad": "5",
        "estado_conservacion": "Bueno", "acabados": "Estándar", "cochera": "1",
    }
    v.update({b: "" for b in BOOLEANAS})
    v["transporte_publico"] = "1"
    return v


def desde_formulario(source) -> dict:
    """Toma los campos de un ``request.form``/``request.args`` conservando lo escrito."""
    v = {c: (source.get(c) or "").strip() for c in CAMPOS_TEXTO}
    v.update({b: "1" if source.get(b) else "" for b in BOOLEANAS})
    return v


def precargado(source) -> dict:
    """Valores por defecto sobrescritos por parámetros de la URL (formulario rápido del inicio)."""
    v = valores_por_defecto()
    for c in CAMPOS_TEXTO:
        if source.get(c):
            v[c] = source.get(c).strip()
    for b in BOOLEANAS:
        if b in source:
            v[b] = "1" if source.get(b) in ("1", "on", "true") else ""
    return v


def desde_propiedad(p) -> dict:
    v = {c: str(getattr(p, c)) for c in CAMPOS_TEXTO}
    v.update({b: "1" if getattr(p, b) else "" for b in BOOLEANAS})
    return v
