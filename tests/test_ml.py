import numpy as np

from app.ml.constants import FEATURE_COLUMNS
from app.ml.datagen import generar_dataset
from app.ml.pipeline import DatosInsuficientes, entrenar, explicar, predecir
from app.ml.schema import limpiar_vivienda

import pytest


def test_dataset_sintetico_valido():
    df = generar_dataset(300, 1)
    assert len(df) == 300
    assert list(df.columns) == FEATURE_COLUMNS + ["precio"]
    assert df.precio.min() >= 60000 and not df.isna().any().any()
    assert (df[df.tipo == "Departamento"].area_terreno == df[df.tipo == "Departamento"].area_construida).all()


def test_entrenamiento_compara_dos_algoritmos(modelo_compartido):
    _, m = modelo_compartido
    assert set(m["algoritmos"]) == {"random_forest", "gradient_boosting"}
    assert m["ganador"] in m["algoritmos"]
    prueba = m["algoritmos"][m["ganador"]]["prueba"]
    assert prueba["r2"] > 0.7 and prueba["mae"] > 0 and prueba["rmse"] >= prueba["mae"]
    assert m["n_total"] == m["n_entrenamiento"] + m["n_validacion"] + m["n_prueba"]
    assert len(m["importancias"]) == len(FEATURE_COLUMNS)


def test_pocos_datos_se_rechazan():
    with pytest.raises(DatosInsuficientes):
        entrenar(generar_dataset(20, 1), minimo_filas=60)


def test_prediccion_razonable(modelo_compartido):
    import joblib

    carpeta, _ = modelo_compartido
    bundle = joblib.load(carpeta / "modelo_v1.joblib")  # el original compartido nunca se modifica
    base = limpiar_vivienda(
        {"tipo": "Departamento", "distrito": "Cayma", "area_construida": "80", "habitaciones": "3", "banos": "2", "antiguedad": "5"}
    )[0]
    grande = dict(base, area_construida=160.0, area_terreno=160.0)
    barato = dict(base, distrito="Yura")
    p_base, p_grande, p_barato = predecir(bundle, [base, grande, barato])
    assert p_grande > p_base * 1.4          # más área → más precio
    assert p_barato < p_base                # Yura es más económico que Cayma
    assert all(np.isfinite([p_base, p_grande, p_barato]))
    factores = explicar(bundle, base)
    assert factores and all("impacto" in f and "etiqueta" in f for f in factores)


def test_validacion_vivienda():
    ok, errs = limpiar_vivienda(
        {"tipo": "duplex", "distrito": "jose luis bustamante", "area_construida": "130,5", "habitaciones": "4", "banos": "3", "antiguedad": "2"}
    )
    assert not errs
    assert ok["tipo"] == "Dúplex" and ok["distrito"] == "José Luis Bustamante y Rivero"
    assert ok["pisos"] == 2 and ok["area_construida"] == 130.5 and ok["area_terreno"] == 65.2

    dep, errs = limpiar_vivienda(
        {"tipo": "Departamento", "distrito": "Cayma", "area_construida": "90", "area_terreno": "500", "habitaciones": "2", "banos": "1", "antiguedad": "0"}
    )
    assert not errs and dep["area_terreno"] == 90.0 and dep["pisos"] == 1

    _, errs = limpiar_vivienda({"tipo": "Castillo", "distrito": "Luna", "area_construida": "-4", "habitaciones": "x", "banos": "", "antiguedad": "500"})
    assert len(errs) >= 5

    _, errs = limpiar_vivienda(
        {"tipo": "Casa", "distrito": "Cayma", "area_construida": "300", "pisos": "1", "area_terreno": "100", "habitaciones": "3", "banos": "2", "antiguedad": "1"}
    )
    assert any("terreno" in e.lower() for e in errs)

    _, errs = limpiar_vivienda(
        {"tipo": "Casa", "distrito": "Cayma", "area_construida": "100", "habitaciones": "3", "banos": "2", "antiguedad": "1", "precio": "30000"},
        exigir_precio=True,
    )
    assert any("por m²" in e for e in errs)
