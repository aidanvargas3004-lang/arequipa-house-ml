"""Entrenamiento, evaluación, predicción y explicación del modelo de tasación.

Se entrenan dos regresores (Random Forest y Gradient Boosting) sobre el
logaritmo del precio, se comparan con MAE, RMSE y R² y se conserva el mejor
según el RMSE de validación. Las métricas definitivas se reportan sobre un
conjunto de prueba que no participó en la selección.
"""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .constants import (
    ACABADOS,
    BOOLEANAS,
    CATEGORICAS,
    ESTADOS,
    ETIQUETAS,
    FEATURE_COLUMNS,
    NUMERICAS,
    TARGET,
)

ALGORITMOS = {
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting",
}

_IDX_ESTADO = {e: i for i, e in enumerate(ESTADOS)}
_IDX_ACABADO = {a: i for i, a in enumerate(ACABADOS)}


class DatosInsuficientes(ValueError):
    """No hay suficientes registros para entrenar un modelo confiable."""


# --------------------------------------------------------------------- datos
def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte un DataFrame con nombres legibles en la matriz numérica del modelo."""
    faltan = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas: {', '.join(faltan)}")
    x = df[FEATURE_COLUMNS].copy()
    x["estado_conservacion"] = x["estado_conservacion"].map(_IDX_ESTADO)
    x["acabados"] = x["acabados"].map(_IDX_ACABADO)
    for col in NUMERICAS:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    if x[NUMERICAS].isna().any().any():
        raise ValueError("Hay valores no numéricos o categorías desconocidas en los datos.")
    x[NUMERICAS] = x[NUMERICAS].astype(float)
    return x


def _construir(algoritmo: str, semilla: int, n_jobs: int):
    if algoritmo == "random_forest":
        est = RandomForestRegressor(
            n_estimators=160, min_samples_leaf=2, max_features=0.6, n_jobs=n_jobs, random_state=semilla
        )
    elif algoritmo == "gradient_boosting":
        est = GradientBoostingRegressor(
            n_estimators=350, learning_rate=0.07, max_depth=4, subsample=0.9, random_state=semilla
        )
    else:  # pragma: no cover
        raise ValueError(algoritmo)
    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAS)],
        remainder="passthrough",
    )
    return TransformedTargetRegressor(
        regressor=Pipeline([("pre", pre), ("est", est)]), func=np.log1p, inverse_func=np.expm1
    )


def _metricas(y_real, y_pred) -> dict:
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ape = np.abs(y_pred - y_real) / y_real
    return {
        "mae": round(float(mean_absolute_error(y_real, y_pred)), 2),
        "rmse": round(float(math.sqrt(mean_squared_error(y_real, y_pred))), 2),
        "r2": round(float(r2_score(y_real, y_pred)), 4),
        "mape": round(float(ape.mean() * 100), 2),
        "mdape": round(float(np.median(ape) * 100), 2),
    }


def _referencia(x_tr: pd.DataFrame, df_tr: pd.DataFrame) -> dict:
    """Vivienda 'típica' (mediana/moda) contra la que se mide el aporte de cada variable."""
    ref: dict = {c: str(df_tr[c].mode().iloc[0]) for c in CATEGORICAS}
    for col in NUMERICAS:
        mediana = float(x_tr[col].median())
        if col == "estado_conservacion":
            ref[col] = ESTADOS[int(round(mediana))]
        elif col == "acabados":
            ref[col] = ACABADOS[int(round(mediana))]
        elif col in BOOLEANAS or col in ("habitaciones", "banos", "pisos", "antiguedad", "cochera"):
            ref[col] = int(round(mediana))
        else:
            ref[col] = round(mediana, 1)
    return ref


def entrenar(df: pd.DataFrame, *, semilla: int = 42, n_jobs: int = 1, minimo_filas: int = 60) -> dict:
    """Entrena y compara ambos algoritmos. Devuelve ``{"bundle": …, "metricas": …}``."""
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET]).reset_index(drop=True)
    if len(df) < minimo_filas:
        raise DatosInsuficientes(
            f"Se requieren al menos {minimo_filas} registros válidos para entrenar (hay {len(df)})."
        )
    x = preparar(df)
    y = df[TARGET].astype(float).to_numpy()

    idx = np.arange(len(df))
    i_tr, i_tmp = train_test_split(idx, test_size=0.30, random_state=semilla)
    i_val, i_te = train_test_split(i_tmp, test_size=0.50, random_state=semilla)

    resultados: dict = {}
    modelos: dict = {}
    for algoritmo in ALGORITMOS:
        est = _construir(algoritmo, semilla, n_jobs)
        est.fit(x.iloc[i_tr], y[i_tr])
        modelos[algoritmo] = est
        resultados[algoritmo] = {
            "validacion": _metricas(y[i_val], est.predict(x.iloc[i_val])),
            "prueba": _metricas(y[i_te], est.predict(x.iloc[i_te])),
        }

    ganador = min(resultados, key=lambda a: resultados[a]["validacion"]["rmse"])
    modelo = modelos[ganador]

    # Importancia global de variables (permutación sobre validación)
    imp = permutation_importance(
        modelo, x.iloc[i_val], y[i_val], n_repeats=3, random_state=semilla, n_jobs=1
    )
    pesos = np.clip(imp.importances_mean, 0, None)
    total = pesos.sum() or 1.0
    importancias = sorted(
        (
            {"campo": c, "etiqueta": ETIQUETAS[c], "peso": round(float(p / total * 100), 2)}
            for c, p in zip(FEATURE_COLUMNS, pesos)
        ),
        key=lambda d: d["peso"],
        reverse=True,
    )

    referencia = _referencia(x.iloc[i_tr], df.iloc[i_tr])
    error_rel = resultados[ganador]["validacion"]["mdape"] / 100.0

    bundle = {
        "modelo": modelo,
        "algoritmo": ganador,
        "referencia": referencia,
        "error_relativo": error_rel,
        "columnas": FEATURE_COLUMNS,
        "sklearn": sklearn.__version__,
        "entrenado_en": datetime.now(timezone.utc).isoformat(),
    }
    metricas = {
        "ganador": ganador,
        "algoritmos": resultados,
        "importancias": importancias,
        "n_total": int(len(df)),
        "n_entrenamiento": int(len(i_tr)),
        "n_validacion": int(len(i_val)),
        "n_prueba": int(len(i_te)),
    }
    return {"bundle": bundle, "metricas": metricas}


# ---------------------------------------------------------------- persistencia
def guardar(bundle: dict, ruta) -> None:
    joblib.dump(bundle, ruta, compress=3)


def cargar(ruta) -> dict:
    return joblib.load(ruta)


def a_bytes(bundle: dict) -> bytes:  # útil para pruebas
    buf = io.BytesIO()
    joblib.dump(bundle, buf, compress=3)
    return buf.getvalue()


# ------------------------------------------------------------------ predicción
def predecir(bundle: dict, registros: list[dict]) -> np.ndarray:
    """Predice el precio (S/) de una o más viviendas (diccionarios con nombres legibles)."""
    df = pd.DataFrame(registros, columns=FEATURE_COLUMNS)
    return bundle["modelo"].predict(preparar(df))


def formato_valor(campo: str, valor) -> str:
    if campo in BOOLEANAS:
        return "Sí" if valor else "No"
    if campo in ("area_terreno", "area_construida"):
        return f"{float(valor):g} m²"
    if campo == "antiguedad":
        return "A estrenar" if int(valor) == 0 else f"{int(valor)} años"
    return str(valor)


def explicar(bundle: dict, registro: dict, *, maximo: int = 8) -> list[dict]:
    """Aporte aproximado (S/) de cada variable frente a una vivienda típica.

    Método de oclusión: se reemplaza cada variable por su valor de referencia
    y se mide cuánto cambia el precio estimado. Un valor positivo indica que la
    característica SUBE el precio respecto a lo habitual.
    """
    ref = bundle["referencia"]
    base = {c: registro[c] for c in FEATURE_COLUMNS}
    filas = [base]
    campos = []
    for campo in FEATURE_COLUMNS:
        if registro["tipo"] == "Departamento" and campo in ("area_terreno", "pisos"):
            continue
        if base[campo] == ref[campo]:
            continue
        variante = dict(base)
        variante[campo] = ref[campo]
        filas.append(variante)
        campos.append(campo)

    if not campos:
        return []
    precios = predecir(bundle, filas)
    precio = float(precios[0])
    factores = []
    for campo, p_ref in zip(campos, precios[1:]):
        delta = precio - float(p_ref)
        if abs(delta) < 0.004 * precio:
            continue
        factores.append(
            {
                "campo": campo,
                "etiqueta": ETIQUETAS[campo],
                "valor": formato_valor(campo, base[campo]),
                "referencia": formato_valor(campo, ref[campo]),
                "impacto": delta,
            }
        )
    factores.sort(key=lambda f: abs(f["impacto"]), reverse=True)
    return factores[:maximo]
