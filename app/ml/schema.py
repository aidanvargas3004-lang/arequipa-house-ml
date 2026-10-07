"""Validación y normalización de registros de vivienda.

La misma lógica se usa en los formularios (tasación, publicación, dataset) y en
la carga masiva de archivos CSV, de modo que el modelo solo recibe datos limpios.
"""
from __future__ import annotations

import unicodedata

from .constants import (
    ACABADOS,
    BOOLEANAS,
    DISTRITO_NOMBRES,
    ESTADOS,
    ETIQUETAS,
    LIMITES,
    TIPOS,
)


def norm(texto) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (para comparar textos)."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().strip().split())


_TIPOS = {norm(t): t for t in TIPOS}
_TIPOS.update({"duplex": "Dúplex", "depa": "Departamento", "dpto": "Departamento", "depto": "Departamento"})

_DISTRITOS = {norm(d): d for d in DISTRITO_NOMBRES}
_DISTRITOS.update(
    {
        "arequipa": "Arequipa (Cercado)",
        "cercado": "Arequipa (Cercado)",
        "cercado de arequipa": "Arequipa (Cercado)",
        "jose luis bustamante": "José Luis Bustamante y Rivero",
        "jlbyr": "José Luis Bustamante y Rivero",
        "jlb": "José Luis Bustamante y Rivero",
        "jlbr": "José Luis Bustamante y Rivero",
        "j. hunter": "Jacobo Hunter",
        "hunter": "Jacobo Hunter",
    }
)
_ESTADOS = {norm(e): e for e in ESTADOS}
_ACABADOS = {norm(a): a for a in ACABADOS}
_ACABADOS.update({"alta": "Alta calidad", "estandar": "Estándar", "basico": "Básico"})

# Valores por defecto cuando el campo viene vacío (p. ej. en un CSV incompleto)
DEFAULTS = {
    "estado_conservacion": "Bueno",
    "acabados": "Estándar",
    "cochera": 0,
    "pisos": None,  # depende del tipo
    **{b: 0 for b in BOOLEANAS},
}

_VERDADERO = {"1", "true", "si", "s", "yes", "y", "on", "x", "t", "verdadero"}
_FALSO = {"", "0", "false", "no", "n", "off", "f", "falso"}


def _num(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace(" ", "")
    if s == "":
        return None
    # "1.250,50" o "1250,5" → 1250.5
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    for simbolo in ("s/", "S/", "$"):
        s = s.replace(simbolo, "")
    return float(s)


def _bool(valor):
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return 1 if valor else 0
    s = norm(valor)
    if s in _VERDADERO:
        return 1
    if s in _FALSO:
        return 0
    return None


def _entero(valor, nombre, errores, minimo, maximo, *, obligatorio=True, defecto=None):
    try:
        n = _num(valor)
    except ValueError:
        errores.append(f"{nombre}: '{valor}' no es un número válido.")
        return None
    if n is None:
        if defecto is not None:
            return defecto
        if obligatorio:
            errores.append(f"{nombre}: es obligatorio.")
        return None
    if abs(n - round(n)) > 1e-9:
        errores.append(f"{nombre}: debe ser un número entero.")
        return None
    n = int(round(n))
    if not minimo <= n <= maximo:
        errores.append(f"{nombre}: debe estar entre {minimo} y {maximo}.")
        return None
    return n


def _decimal(valor, nombre, errores, minimo, maximo, *, obligatorio=True):
    try:
        n = _num(valor)
    except ValueError:
        errores.append(f"{nombre}: '{valor}' no es un número válido.")
        return None
    if n is None:
        if obligatorio:
            errores.append(f"{nombre}: es obligatorio.")
        return None
    if not minimo <= n <= maximo:
        errores.append(f"{nombre}: debe estar entre {minimo:g} y {maximo:g}.")
        return None
    return round(n, 1)


def limpiar_vivienda(raw: dict, *, exigir_precio: bool = False):
    """Valida y normaliza un diccionario con datos de una vivienda.

    Devuelve ``(datos, errores)``. Si ``errores`` no está vacío, ``datos`` no
    debe usarse. Los valores vacíos toman los ``DEFAULTS`` cuando existen.
    """
    errores: list[str] = []
    datos: dict = {}

    tipo = _TIPOS.get(norm(raw.get("tipo")))
    if not tipo:
        errores.append(f"{ETIQUETAS['tipo']}: elige uno de {', '.join(TIPOS)}.")
    datos["tipo"] = tipo

    distrito = _DISTRITOS.get(norm(raw.get("distrito")))
    if not distrito:
        errores.append(f"{ETIQUETAS['distrito']}: '{raw.get('distrito') or ''}' no es un distrito soportado.")
    datos["distrito"] = distrito

    datos["area_construida"] = _decimal(
        raw.get("area_construida"), ETIQUETAS["area_construida"], errores, *LIMITES["area_construida"]
    )

    pisos_defecto = 2 if tipo == "Dúplex" else 1
    datos["pisos"] = _entero(
        raw.get("pisos"), ETIQUETAS["pisos"], errores, *LIMITES["pisos"], defecto=pisos_defecto
    )

    terreno = _decimal(
        raw.get("area_terreno"), ETIQUETAS["area_terreno"], errores, *LIMITES["area_terreno"], obligatorio=False
    )
    if tipo == "Departamento":
        terreno = datos["area_construida"]  # el terreno de un departamento es su propia área
        if datos["pisos"] is not None:
            datos["pisos"] = 1
    elif terreno is None and datos["area_construida"] is not None and datos["pisos"]:
        terreno = round(datos["area_construida"] / datos["pisos"], 1)
    datos["area_terreno"] = terreno

    if tipo in ("Casa", "Dúplex") and terreno and datos["area_construida"] and datos["pisos"]:
        por_piso = datos["area_construida"] / datos["pisos"]
        if terreno < por_piso * 0.95:
            errores.append(
                f"{ETIQUETAS['area_terreno']}: no puede ser menor que el área construida por piso "
                f"({por_piso:.0f} m²)."
            )

    datos["habitaciones"] = _entero(
        raw.get("habitaciones"), ETIQUETAS["habitaciones"], errores, *LIMITES["habitaciones"]
    )
    datos["banos"] = _entero(raw.get("banos"), ETIQUETAS["banos"], errores, *LIMITES["banos"])
    datos["antiguedad"] = _entero(
        raw.get("antiguedad"), ETIQUETAS["antiguedad"], errores, *LIMITES["antiguedad"]
    )
    datos["cochera"] = _entero(
        raw.get("cochera"), ETIQUETAS["cochera"], errores, *LIMITES["cochera"], defecto=DEFAULTS["cochera"]
    )

    estado = raw.get("estado_conservacion")
    if estado is None or str(estado).strip() == "":
        estado = DEFAULTS["estado_conservacion"]
    datos["estado_conservacion"] = _ESTADOS.get(norm(estado))
    if not datos["estado_conservacion"]:
        errores.append(f"{ETIQUETAS['estado_conservacion']}: elige uno de {', '.join(ESTADOS)}.")

    acabados = raw.get("acabados")
    if acabados is None or str(acabados).strip() == "":
        acabados = DEFAULTS["acabados"]
    datos["acabados"] = _ACABADOS.get(norm(acabados))
    if not datos["acabados"]:
        errores.append(f"{ETIQUETAS['acabados']}: elige uno de {', '.join(ACABADOS)}.")

    for campo in BOOLEANAS:
        v = _bool(raw.get(campo))
        if v is None:
            errores.append(f"{ETIQUETAS[campo]}: valor no válido (use sí/no).")
        datos[campo] = v

    if exigir_precio:
        datos["precio"] = _decimal(raw.get("precio"), "Precio", errores, *LIMITES["precio"])
        precio, area = datos.get("precio"), datos.get("area_construida")
        if precio and area and not 500 <= precio / area <= 30000:
            errores.append(
                f"Precio: S/ {precio / area:,.0f} por m² construido está fuera de un rango razonable "
                "(S/ 500 – S/ 30,000)."
            )

    if datos.get("habitaciones") is not None and datos.get("banos") is not None:
        if datos["habitaciones"] == 0 and tipo == "Casa":
            errores.append(f"{ETIQUETAS['habitaciones']}: una casa debe tener al menos 1 habitación.")

    return datos, errores
