"""Generador del dataset SINTÉTICO de demostración.

Simula un mercado inmobiliario de Arequipa mediante un modelo hedónico
(precio = valor base por distrito × características × ruido). NO son datos
reales: sirven para poner en marcha el sistema hasta contar con el histórico
de la empresa, que se carga luego desde el panel de administrador (CSV).

Los precios base por distrito están en ``constants.DISTRITOS``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import ACABADOS, DISTRITOS, ESTADOS, FEATURE_COLUMNS, TARGET

_F_TIPO = {"Casa": 1.0, "Departamento": 1.05, "Dúplex": 1.08}
_F_ACABADOS = {"Básico": 0.82, "Estándar": 1.0, "Alta calidad": 1.17, "Lujo": 1.38}
_F_ESTADO = {"Malo": 0.78, "Regular": 0.9, "Bueno": 1.0, "Excelente": 1.07}


def valor_hedonico(fila: dict, rng: np.random.Generator | None = None, ruido: float = 0.0) -> float:
    """Precio (S/) de una vivienda según el modelo hedónico del simulador."""
    d = DISTRITOS[fila["distrito"]]
    pm2 = d["pm2"]
    construida = fila["area_construida"]
    terreno = fila["area_terreno"]

    depreciacion = max(0.45, 1.0 - 0.0085 * fila["antiguedad"])
    valor = construida * pm2 * _F_TIPO[fila["tipo"]] * _F_ACABADOS[fila["acabados"]]
    valor *= _F_ESTADO[fila["estado_conservacion"]] * depreciacion

    if fila["tipo"] != "Departamento":
        excedente = max(0.0, terreno - construida / max(1, fila["pisos"]))
        valor += excedente * pm2 * 0.38  # valor del terreno libre

    valor += fila["cochera"] * 22000
    valor += 18000 * fila["jardin"] + 38000 * fila["piscina"]
    valor *= 1 + 0.035 * fila["ascensor"] + 0.03 * fila["seguridad"]
    valor *= 1 + 0.012 * fila["cerca_colegios"] + 0.012 * fila["cerca_hospitales"]
    valor *= 1 + 0.015 * fila["cerca_comercial"] + 0.01 * fila["transporte_publico"]
    valor += 6000 * max(0, fila["banos"] - 1)
    if ruido and rng is not None:
        valor *= float(np.exp(rng.normal(0, ruido)))
    return float(valor)


def generar_dataset(n: int = 4000, semilla: int = 42) -> pd.DataFrame:
    """Devuelve un DataFrame con ``FEATURE_COLUMNS`` + ``precio``."""
    rng = np.random.default_rng(semilla)
    nombres = list(DISTRITOS)
    # Más oferta en distritos con mayor población
    pesos = np.array([6, 9, 7, 7, 4, 4, 5, 8, 7, 5, 5, 2, 4, 3, 2, 2, 2], dtype=float)
    pesos = pesos[: len(nombres)] / pesos[: len(nombres)].sum()

    filas = []
    for _ in range(n):
        tipo = rng.choice(["Casa", "Departamento", "Dúplex"], p=[0.5, 0.38, 0.12])
        distrito = str(rng.choice(nombres, p=pesos))
        nivel = DISTRITOS[distrito]["nivel"]

        if tipo == "Departamento":
            construida = float(np.clip(rng.lognormal(np.log(88), 0.32), 38, 260))
            pisos = 1
            terreno = construida
        elif tipo == "Dúplex":
            construida = float(np.clip(rng.lognormal(np.log(140), 0.3), 80, 380))
            pisos = 2
            terreno = construida / 2 * rng.uniform(1.0, 1.5)
        else:
            construida = float(np.clip(rng.lognormal(np.log(150), 0.4), 55, 600))
            pisos = int(rng.choice([1, 2, 3], p=[0.35, 0.5, 0.15]))
            terreno = construida / pisos * rng.uniform(1.0, 2.3)
        construida = round(construida, 1)
        terreno = round(max(terreno, construida / pisos), 1) if tipo != "Departamento" else construida

        habitaciones = int(np.clip(round(construida / 32 + rng.normal(0, 0.7)), 1, 9))
        banos = int(np.clip(round(habitaciones * 0.7 + rng.normal(0, 0.55)), 1, 7))
        antiguedad = int(np.clip(rng.exponential(13), 0, 70))

        # Estado: se deteriora con la edad
        p_malo = min(0.5, 0.01 + antiguedad / 120)
        p_regular = min(0.5, 0.05 + antiguedad / 60)
        p_exc = max(0.03, 0.4 - antiguedad / 40)
        p_bueno = max(0.05, 1 - p_malo - p_regular - p_exc)
        probs = np.array([p_malo, p_regular, p_bueno, p_exc])
        estado = str(rng.choice(ESTADOS, p=probs / probs.sum()))

        base_acab = np.array([[0.45, 0.45, 0.09, 0.01], [0.2, 0.5, 0.26, 0.04], [0.08, 0.4, 0.4, 0.12], [0.03, 0.27, 0.45, 0.25]])[nivel]
        acabados = str(rng.choice(ACABADOS, p=base_acab))

        es_dep = tipo == "Departamento"
        cochera = int(rng.choice([0, 1, 2, 3], p=[0.12, 0.55, 0.28, 0.05] if not es_dep else [0.35, 0.55, 0.09, 0.01]))
        fila = {
            "tipo": tipo,
            "distrito": distrito,
            "area_terreno": terreno,
            "area_construida": construida,
            "habitaciones": habitaciones,
            "banos": banos,
            "pisos": pisos,
            "antiguedad": antiguedad,
            "estado_conservacion": estado,
            "acabados": acabados,
            "cochera": cochera,
            "jardin": int(rng.random() < (0.06 if es_dep else 0.5)),
            "piscina": int(rng.random() < (0.05 if es_dep else 0.07 + 0.03 * nivel)),
            "ascensor": int(rng.random() < (0.55 + 0.1 * (nivel >= 2) if es_dep else 0.02)),
            "seguridad": int(rng.random() < 0.15 + 0.12 * nivel),
            "cerca_colegios": int(rng.random() < 0.7),
            "cerca_hospitales": int(rng.random() < 0.4),
            "cerca_comercial": int(rng.random() < 0.5),
            "transporte_publico": int(rng.random() < 0.8),
        }
        precio = valor_hedonico(fila, rng, ruido=0.07)
        fila[TARGET] = int(max(60000, round(precio / 500) * 500))
        filas.append(fila)

    return pd.DataFrame(filas, columns=FEATURE_COLUMNS + [TARGET])
