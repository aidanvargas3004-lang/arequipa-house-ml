"""Lógica de negocio: dataset, modelos, parámetros y estimación de precios."""
from __future__ import annotations

import io
import threading
from datetime import timedelta
from pathlib import Path

import pandas as pd
from flask import current_app
from sqlalchemy import func

from .extensions import db
from .ml import pipeline
from .ml.constants import FEATURE_COLUMNS, TARGET, DISTRITO_NOMBRES
from .ml.datagen import generar_dataset
from .ml.schema import limpiar_vivienda, norm
from .models import AjusteDistrito, DatasetRegistro, ModeloML, Parametro, Tasacion, ahora

COLUMNAS_DATASET = FEATURE_COLUMNS + [TARGET]

# ------------------------------------------------------------------ parámetros
PARAMETROS_BASE = {
    "factor_mercado": ("1.0", "Factor global de mercado (1.00 = sin ajuste; 1.05 = +5 %)"),
    "margen_extra": ("0.0", "Margen adicional del rango de precio (0.02 = ±2 % extra)"),
}
LIMITES_PARAM = {"factor_mercado": (0.5, 2.0), "margen_extra": (0.0, 0.3)}
LIMITES_AJUSTE = (0.5, 2.0)


def asegurar_parametros() -> None:
    for clave, (valor, desc) in PARAMETROS_BASE.items():
        if db.session.get(Parametro, clave) is None:
            db.session.add(Parametro(clave=clave, valor=valor, descripcion=desc))
    for d in DISTRITO_NOMBRES:
        if db.session.get(AjusteDistrito, d) is None:
            db.session.add(AjusteDistrito(distrito=d, factor=1.0))
    db.session.commit()


def obtener_parametro(clave: str) -> float:
    p = db.session.get(Parametro, clave)
    try:
        return float(p.valor) if p else float(PARAMETROS_BASE[clave][0])
    except ValueError:
        return float(PARAMETROS_BASE[clave][0])


def guardar_parametro(clave: str, valor: float) -> None:
    minimo, maximo = LIMITES_PARAM[clave]
    if not minimo <= valor <= maximo:
        raise ValueError(f"El valor debe estar entre {minimo:g} y {maximo:g}.")
    p = db.session.get(Parametro, clave)
    if p is None:
        p = Parametro(clave=clave, valor=str(valor), descripcion=PARAMETROS_BASE[clave][1])
        db.session.add(p)
    p.valor = repr(float(valor))


def ajuste_distrito(distrito: str) -> float:
    a = db.session.get(AjusteDistrito, distrito)
    return float(a.factor) if a else 1.0


# --------------------------------------------------------------------- dataset
def _a_python(v):
    return v.item() if hasattr(v, "item") else v


def dataset_df() -> pd.DataFrame:
    filas = db.session.query(DatasetRegistro).all()
    return pd.DataFrame(
        [{c: getattr(r, c) for c in COLUMNAS_DATASET} for r in filas], columns=COLUMNAS_DATASET
    )


def composicion_dataset() -> dict:
    filas = db.session.query(DatasetRegistro.origen, func.count()).group_by(DatasetRegistro.origen).all()
    return {origen: int(n) for origen, n in filas}


def cargar_sintetico(n: int | None = None, semilla: int = 42) -> int:
    n = n or current_app.config["ML_SYNTHETIC_ROWS"]
    df = generar_dataset(n, semilla)
    registros = [{k: _a_python(v) for k, v in fila.items()} | {"origen": "sintetico"} for fila in df.to_dict("records")]
    db.session.bulk_insert_mappings(DatasetRegistro, registros)
    db.session.commit()
    return len(registros)


def agregar_registro(datos: dict, origen: str) -> DatasetRegistro:
    """``datos`` ya validado con ``limpiar_vivienda(exigir_precio=True)``."""
    reg = DatasetRegistro(**{c: datos[c] for c in COLUMNAS_DATASET}, origen=origen)
    db.session.add(reg)
    return reg


_ALIAS_COLUMNAS = {
    "baños": "banos", "bano": "banos", "banhos": "banos",
    "dormitorios": "habitaciones", "cuartos": "habitaciones", "hab": "habitaciones", "habitacion": "habitaciones",
    "area": "area_construida", "m2": "area_construida", "area_techada": "area_construida",
    "construida": "area_construida", "area_const": "area_construida",
    "terreno": "area_terreno", "area_total": "area_terreno", "area_lote": "area_terreno",
    "precio_venta": "precio", "valor": "precio", "precio_soles": "precio", "precio_s": "precio",
    "años": "antiguedad", "anos": "antiguedad", "edad": "antiguedad", "antiguedad_anos": "antiguedad",
    "estado": "estado_conservacion", "conservacion": "estado_conservacion",
    "garaje": "cochera", "cocheras": "cochera", "estacionamiento": "cochera", "estacionamientos": "cochera",
    "ubicacion": "distrito", "zona": "distrito",
    "tipo_inmueble": "tipo", "tipo_vivienda": "tipo", "tipo_propiedad": "tipo",
    "terminados": "acabados", "calidad_acabados": "acabados",
    "colegios": "cerca_colegios", "hospitales": "cerca_hospitales",
    "centro_comercial": "cerca_comercial", "comercio": "cerca_comercial",
    "transporte": "transporte_publico",
}
_REQUERIDAS_CSV = ["tipo", "distrito", "area_construida", "habitaciones", "banos", "antiguedad", "precio"]


def _normalizar_columna(nombre: str) -> str:
    n = norm(nombre).replace(" ", "_").replace("-", "_")
    return _ALIAS_COLUMNAS.get(n, _ALIAS_COLUMNAS.get(str(nombre).strip().lower(), n))


def importar_csv(contenido: bytes, *, reemplazar_sinteticos: bool = False, max_filas: int = 20000) -> dict:
    """Importa registros históricos desde un CSV. Devuelve un resumen del proceso."""
    df = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(
                io.BytesIO(contenido), sep=None, engine="python", encoding=codificacion,
                dtype=str, keep_default_na=False,
            )
            break
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
    if df is None or df.empty:
        raise ValueError("No se pudo leer el archivo o está vacío. Use un CSV con encabezados.")
    if len(df) > max_filas:
        raise ValueError(f"El archivo supera el máximo de {max_filas:,} filas.")

    df.columns = [_normalizar_columna(c) for c in df.columns]
    faltan = [c for c in _REQUERIDAS_CSV if c not in df.columns]
    if faltan:
        raise ValueError(
            "Faltan columnas obligatorias: " + ", ".join(faltan)
            + ". Columnas requeridas: " + ", ".join(_REQUERIDAS_CSV) + "."
        )

    validos, errores, vistos = [], [], set()
    for n_fila, raw in enumerate(df.to_dict("records"), start=2):
        datos, errs = limpiar_vivienda(raw, exigir_precio=True)
        if errs:
            errores.append(f"Fila {n_fila}: {errs[0]}")
            continue
        clave = tuple(datos[c] for c in COLUMNAS_DATASET)
        if clave in vistos:
            errores.append(f"Fila {n_fila}: registro duplicado dentro del archivo.")
            continue
        vistos.add(clave)
        validos.append({c: datos[c] for c in COLUMNAS_DATASET} | {"origen": "csv"})

    if not validos:
        raise ValueError("Ningún registro del archivo es válido. Primer error: " + (errores[0] if errores else "—"))

    advertencias, eliminados = [], 0
    minimo = current_app.config["ML_MIN_ROWS"]
    if reemplazar_sinteticos:
        if len(validos) >= minimo:
            eliminados = DatasetRegistro.query.filter_by(origen="sintetico").delete()
        else:
            advertencias.append(
                f"Se conservaron los datos sintéticos: el archivo aporta menos de {minimo} registros válidos."
            )
    db.session.bulk_insert_mappings(DatasetRegistro, validos)
    db.session.commit()
    return {
        "importados": len(validos),
        "omitidos": len(errores),
        "errores": errores[:25],
        "eliminados_sinteticos": eliminados,
        "advertencias": advertencias,
    }


# ---------------------------------------------------------------------- modelos
_cache = {"id": None, "bundle": None}
_lock = threading.Lock()


class EntrenamientoEnCurso(RuntimeError):
    pass


def carpeta_modelos() -> Path:
    p = Path(current_app.config["MODELS_FOLDER"])
    p.mkdir(parents=True, exist_ok=True)
    return p


def modelo_activo() -> ModeloML | None:
    return ModeloML.query.filter_by(activo=True, estado="listo").first()


def _siguiente_version() -> int:
    return (db.session.query(func.max(ModeloML.version)).scalar() or 0) + 1


def _entrenar_en_registro(modelo: ModeloML) -> None:
    cfg = current_app.config
    resultado = pipeline.entrenar(
        dataset_df(),
        semilla=cfg["ML_RANDOM_STATE"],
        n_jobs=cfg["ML_N_JOBS"],
        minimo_filas=cfg["ML_MIN_ROWS"],
    )
    archivo = f"modelo_v{modelo.version}.joblib"
    pipeline.guardar(resultado["bundle"], carpeta_modelos() / archivo)
    modelo.algoritmo = resultado["metricas"]["ganador"]
    modelo.archivo = archivo
    modelo.metricas = resultado["metricas"]
    modelo.composicion = composicion_dataset()
    modelo.estado = "listo"
    modelo.error = None
    modelo.terminado_en = ahora()


def activar_modelo(modelo: ModeloML) -> None:
    if modelo.estado != "listo":
        raise ValueError("Solo se puede activar un modelo con entrenamiento finalizado.")
    ModeloML.query.update({ModeloML.activo: False})
    modelo.activo = True
    db.session.commit()
    with _lock:
        _cache["id"] = None


def _ejecutar(modelo_id: int, activar: bool) -> None:
    modelo = db.session.get(ModeloML, modelo_id)
    try:
        _entrenar_en_registro(modelo)
        db.session.commit()
        if activar:
            activar_modelo(modelo)
    except Exception as exc:  # noqa: BLE001 - se informa al administrador
        db.session.rollback()
        modelo = db.session.get(ModeloML, modelo_id)
        modelo.estado = "error"
        modelo.error = str(exc)[:390]
        modelo.terminado_en = ahora()
        db.session.commit()


def _hilo(app, modelo_id: int, activar: bool) -> None:
    with app.app_context():
        try:
            _ejecutar(modelo_id, activar)
        finally:
            db.session.remove()


def lanzar_entrenamiento(usuario_id: int | None, *, activar: bool = True, sincrono: bool = False) -> ModeloML:
    """Crea una nueva versión y la entrena (en segundo plano salvo ``sincrono``).

    El modelo activo sigue atendiendo las estimaciones mientras tanto, por lo
    que el servicio no se interrumpe (CAR-06).
    """
    limite = ahora() - timedelta(minutes=30)
    ModeloML.query.filter(ModeloML.estado == "entrenando", ModeloML.creado_en <= limite).update(
        {ModeloML.estado: "error", ModeloML.error: "Tiempo de entrenamiento agotado."}
    )
    if ModeloML.query.filter(ModeloML.estado == "entrenando").first():
        db.session.commit()
        raise EntrenamientoEnCurso("Ya hay un entrenamiento en curso. Espere a que finalice.")

    modelo = ModeloML(version=_siguiente_version(), estado="entrenando", creado_por_id=usuario_id)
    db.session.add(modelo)
    db.session.commit()
    if sincrono:
        _ejecutar(modelo.id, activar)
    else:
        app = current_app._get_current_object()
        threading.Thread(target=_hilo, args=(app, modelo.id, activar), daemon=True).start()
    return modelo


def asegurar_modelo() -> ModeloML:
    """Garantiza que exista dataset y un modelo activo (autoreparación en el arranque)."""
    if DatasetRegistro.query.count() < current_app.config["ML_MIN_ROWS"]:
        cargar_sintetico()
    activo = modelo_activo()
    if activo:
        return activo
    modelo = lanzar_entrenamiento(None, activar=True, sincrono=True)
    if modelo.estado != "listo":
        raise RuntimeError(f"No se pudo entrenar el modelo inicial: {modelo.error}")
    return modelo


def obtener_bundle() -> tuple[ModeloML, dict]:
    modelo = modelo_activo() or asegurar_modelo()
    with _lock:
        if _cache["id"] == modelo.id and _cache["bundle"] is not None:
            return modelo, _cache["bundle"]
        ruta = carpeta_modelos() / (modelo.archivo or "")
        if not ruta.is_file():
            # El disco es efímero (p. ej. tras un redespliegue): se reentrena con el dataset actual.
            _entrenar_en_registro(modelo)
            db.session.commit()
            ruta = carpeta_modelos() / modelo.archivo
        _cache["bundle"] = pipeline.cargar(ruta)
        _cache["id"] = modelo.id
        return modelo, _cache["bundle"]


def reiniciar_cache() -> None:
    with _lock:
        _cache["id"] = None
        _cache["bundle"] = None


# -------------------------------------------------------------------- estimación
def estimar(datos: dict, *, con_factores: bool = True) -> dict:
    """Estima el precio de una vivienda (datos ya validados)."""
    modelo, bundle = obtener_bundle()
    crudo = float(pipeline.predecir(bundle, [datos])[0])
    mult = obtener_parametro("factor_mercado") * ajuste_distrito(datos["distrito"])
    precio = crudo * mult
    margen = max(0.05, bundle["error_relativo"] + obtener_parametro("margen_extra"))
    resultado = {
        "precio": round(precio / 100) * 100,
        "precio_min": round(precio * (1 - margen) / 100) * 100,
        "precio_max": round(precio * (1 + margen) / 100) * 100,
        "precio_m2": round(precio / datos["area_construida"]),
        "margen": margen,
        "multiplicador": mult,
        "modelo": modelo,
        "factores": [],
    }
    if con_factores:
        factores = pipeline.explicar(bundle, datos)
        for f in factores:
            f["impacto"] = round(f["impacto"] * mult / 10) * 10
        resultado["factores"] = [f for f in factores if f["impacto"] != 0]
    return resultado


def registrar_tasacion(usuario_id: int, datos: dict, est: dict, propiedad_id: int | None = None) -> Tasacion:
    t = Tasacion(
        usuario_id=usuario_id,
        modelo_id=est["modelo"].id,
        propiedad_id=propiedad_id,
        datos=datos,
        precio_estimado=est["precio"],
        precio_min=est["precio_min"],
        precio_max=est["precio_max"],
        precio_m2=est["precio_m2"],
        factores=[{k: v for k, v in f.items()} for f in est["factores"]],
    )
    db.session.add(t)
    db.session.commit()
    return t


def veredicto_precio(precio_publicado: float, precio_estimado: float) -> dict:
    """Compara el precio pedido con el valor estimado por el modelo."""
    dif = (precio_publicado - precio_estimado) / precio_estimado if precio_estimado else 0
    if dif < -0.08:
        etiqueta, clase = "Por debajo del valor estimado", "verde"
    elif dif > 0.08:
        etiqueta, clase = "Por encima del valor estimado", "rojo"
    else:
        etiqueta, clase = "Acorde al valor de mercado", "azul"
    return {"diferencia": dif, "etiqueta": etiqueta, "clase": clase}


# ------------------------------------------------------------------ publicaciones
def eliminar_propiedad(p) -> None:
    """Borra una publicación con sus fotos, mensajes, visitas y favoritos."""
    from .models import Favorito, Mensaje, Visita
    from .utils import borrar_archivo_foto

    nombres = [f.archivo for f in p.fotos]
    Favorito.query.filter_by(propiedad_id=p.id).delete()
    Mensaje.query.filter_by(propiedad_id=p.id).delete()
    Visita.query.filter_by(propiedad_id=p.id).delete()
    Tasacion.query.filter_by(propiedad_id=p.id).update({Tasacion.propiedad_id: None})
    db.session.delete(p)
    db.session.commit()
    for nombre in nombres:
        borrar_archivo_foto(nombre)
