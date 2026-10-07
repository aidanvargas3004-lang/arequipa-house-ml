import io
import time

from app import services
from app.extensions import db
from app.models import AjusteDistrito, DatasetRegistro, ModeloML, Propiedad, Usuario

from .conftest import VIVIENDA, cliente_con_rol, crear_usuario, publicar

CSV_BUENO = (
    "tipo,distrito,area_construida,habitaciones,baños,antigüedad,precio\n"
    "Departamento,Cayma,95,3,2,5,520000\n"
    "Casa,Paucarpata,150,4,3,12,430000\n"
    "Dúplex,Yanahuara,140,3,2,3,780000\n"
)


def subir_csv(admin, contenido, reemplazar=False):
    data = {"archivo": (io.BytesIO(contenido.encode("utf-8")), "datos.csv")}
    if reemplazar:
        data["reemplazar"] = "1"
    return admin.post("/admin/dataset/importar", data=data, content_type="multipart/form-data", follow_redirects=True)


def test_paginas_del_panel_cargan(app):
    admin = cliente_con_rol(app, "administrador")
    for ruta in ("/admin/", "/admin/usuarios", "/admin/publicaciones", "/admin/publicaciones?estado=todas", "/admin/dataset",
                 "/admin/dataset/nuevo", "/admin/modelos", "/admin/modelos/1", "/admin/parametros", "/admin/tasaciones",
                 "/admin/dataset/exportar", "/admin/dataset/plantilla", "/admin/tasaciones/exportar", "/admin/modelos/estado"):
        r = admin.get(ruta)
        assert r.status_code == 200, ruta


def test_gestion_de_usuarios(app):
    admin = cliente_con_rol(app, "administrador")
    uid = crear_usuario(app, "comprador", "x@test.pe")
    admin.post(f"/admin/usuarios/{uid}/actualizar", data={"rol": "vendedor", "activo": "1"})
    with app.app_context():
        assert db.session.get(Usuario, uid).rol == "vendedor"
    admin.post(f"/admin/usuarios/{uid}/actualizar", data={"rol": "vendedor"})  # sin 'activo' → suspendido
    with app.app_context():
        assert db.session.get(Usuario, uid).activo is False
    # No puede degradarse ni suspenderse a sí mismo
    with app.app_context():
        yo = Usuario.query.filter_by(rol="administrador").one().id
    admin.post(f"/admin/usuarios/{yo}/actualizar", data={"rol": "comprador", "activo": "1"})
    with app.app_context():
        assert db.session.get(Usuario, yo).rol == "administrador"
    admin.post("/admin/usuarios/nuevo", data={"nombre": "Otro Admin", "email": "otro@admin.pe", "rol": "administrador", "password": "Clave12345"})
    with app.app_context():
        assert Usuario.query.filter_by(email="otro@admin.pe", rol="administrador").count() == 1


def test_importar_csv(app):
    admin = cliente_con_rol(app, "administrador")
    r = subir_csv(admin, CSV_BUENO)
    assert "3 registros nuevos" in r.get_data(as_text=True)
    with app.app_context():
        assert DatasetRegistro.query.filter_by(origen="csv").count() == 3
        reg = DatasetRegistro.query.filter_by(origen="csv", distrito="Yanahuara").one()
        assert reg.tipo == "Dúplex" and reg.pisos == 2 and reg.estado_conservacion == "Bueno"


def test_importar_csv_con_errores(app):
    admin = cliente_con_rol(app, "administrador")
    malo = CSV_BUENO + "Castillo,Luna,10,0,0,0,5\nCasa,Cayma,100,3,2,5,10\n"
    html = subir_csv(admin, malo).get_data(as_text=True)
    assert "3 registros nuevos" in html and "2 omitidos" in html
    assert "Fila 5" in html
    sin_cols = subir_csv(admin, "a,b\n1,2\n").get_data(as_text=True)
    assert "Faltan columnas obligatorias" in sin_cols
    with app.app_context():
        assert DatasetRegistro.query.filter_by(origen="csv").count() == 3


def test_crud_del_dataset(app):
    admin = cliente_con_rol(app, "administrador")
    r = admin.post("/admin/dataset/nuevo", data={**VIVIENDA, "precio": "480000"})
    assert r.status_code == 302
    with app.app_context():
        reg = DatasetRegistro.query.one()
        assert reg.origen == "manual" and reg.precio == 480000
        rid = reg.id
    assert admin.post(f"/admin/dataset/{rid}/editar", data={**VIVIENDA, "precio": "500000"}).status_code == 302
    assert admin.post("/admin/dataset/nuevo", data={**VIVIENDA, "precio": "5"}).status_code == 422
    admin.post(f"/admin/dataset/{rid}/eliminar")
    with app.app_context():
        assert DatasetRegistro.query.count() == 0


def test_reentrenar_y_activar_modelo(app):
    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        services.cargar_sintetico(400, semilla=5)
        m = services.lanzar_entrenamiento(None, activar=False, sincrono=True)
        assert m.estado == "listo" and m.version == 2 and not m.activo
        assert m.composicion == {"sintetico": 400}
        mid = m.id
    assert admin.get(f"/admin/modelos/{mid}").status_code == 200
    admin.post(f"/admin/modelos/{mid}/activar")
    with app.app_context():
        assert db.session.get(ModeloML, mid).activo and not db.session.get(ModeloML, 1).activo
        assert services.modelo_activo().id == mid
    # un modelo inactivo puede eliminarse; el activo, no
    admin.post(f"/admin/modelos/{mid}/eliminar")
    admin.post("/admin/modelos/1/eliminar")
    with app.app_context():
        assert db.session.get(ModeloML, mid) is not None and db.session.get(ModeloML, 1) is None


def test_entrenar_en_segundo_plano(app):
    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        services.cargar_sintetico(300, semilla=9)
    admin.post("/admin/modelos/entrenar", data={"activar": "1"})
    for _ in range(120):
        with app.app_context():
            estado = db.session.get(ModeloML, 2).estado
        if estado != "entrenando":
            break
        time.sleep(0.25)
    with app.app_context():
        m = db.session.get(ModeloML, 2)
        assert m.estado == "listo" and m.activo, m.error


def test_entrenar_con_pocos_datos_falla_con_mensaje(app):
    with app.app_context():
        m = services.lanzar_entrenamiento(None, sincrono=True)  # el dataset de la prueba está vacío
        assert m.estado == "error" and "al menos" in m.error
        assert services.modelo_activo().version == 1  # el modelo anterior sigue activo


def test_parametros_afectan_la_estimacion(app):
    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        base = services.estimar({"tipo": "Departamento", "distrito": "Cayma", "area_terreno": 100.0, "area_construida": 100.0,
                                 "habitaciones": 3, "banos": 2, "pisos": 1, "antiguedad": 5, "estado_conservacion": "Bueno",
                                 "acabados": "Estándar", "cochera": 1, "jardin": 0, "piscina": 0, "ascensor": 1, "seguridad": 0,
                                 "cerca_colegios": 0, "cerca_hospitales": 0, "cerca_comercial": 0, "transporte_publico": 1})["precio"]
    form = {"factor_mercado": "1.10", "margen_extra": "0.03"}
    form.update({f"ajuste_{d}": "1.00" for d in services.DISTRITO_NOMBRES})
    form["ajuste_Cayma"] = "1.05"
    assert admin.post("/admin/parametros", data=form).status_code == 302
    with app.app_context():
        assert db.session.get(AjusteDistrito, "Cayma").factor == 1.05
        nuevo = services.estimar({"tipo": "Departamento", "distrito": "Cayma", "area_terreno": 100.0, "area_construida": 100.0,
                                  "habitaciones": 3, "banos": 2, "pisos": 1, "antiguedad": 5, "estado_conservacion": "Bueno",
                                  "acabados": "Estándar", "cochera": 1, "jardin": 0, "piscina": 0, "ascensor": 1, "seguridad": 0,
                                  "cerca_colegios": 0, "cerca_hospitales": 0, "cerca_comercial": 0, "transporte_publico": 1})
        assert abs(nuevo["precio"] / base - 1.10 * 1.05) < 0.01
        assert nuevo["margen"] >= 0.08  # mín. 5 % o error del modelo + 3 % extra
    # valores fuera de rango se rechazan
    form["factor_mercado"] = "9"
    admin.post("/admin/parametros", data=form)
    with app.app_context():
        assert services.obtener_parametro("factor_mercado") == 1.10


def test_admin_edita_y_elimina_publicaciones(app):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v)
    from .conftest import datos_publicacion
    r = admin.post("/admin/publicaciones/1/editar", data=datos_publicacion(precio="450000"))
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Propiedad, 1).precio == 450000
        assert db.session.get(Propiedad, 1).estado == "pendiente"
    admin.post("/admin/publicaciones/1/moderar", data={"accion": "eliminar"})
    with app.app_context():
        assert db.session.get(Propiedad, 1) is None


def test_exportaciones_csv(app):
    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        services.cargar_sintetico(50, semilla=3)
    r = admin.get("/admin/dataset/exportar")
    assert r.mimetype == "text/csv" and r.get_data(as_text=True).count("\n") >= 51


def test_autoreparacion_si_falta_el_archivo_del_modelo(app):
    """En hosting con disco efímero el .joblib puede desaparecer: el sistema reentrena solo."""
    from pathlib import Path

    with app.app_context():
        services.cargar_sintetico(300, semilla=4)
        (Path(app.config["MODELS_FOLDER"]) / "modelo_v1.joblib").unlink()
        services.reiniciar_cache()
        est = services.estimar({"tipo": "Casa", "distrito": "Cayma", "area_terreno": 200.0, "area_construida": 150.0,
                                "habitaciones": 3, "banos": 2, "pisos": 2, "antiguedad": 8, "estado_conservacion": "Bueno",
                                "acabados": "Estándar", "cochera": 1, "jardin": 1, "piscina": 0, "ascensor": 0, "seguridad": 0,
                                "cerca_colegios": 1, "cerca_hospitales": 0, "cerca_comercial": 0, "transporte_publico": 1})
        assert est["precio"] > 0
        assert (Path(app.config["MODELS_FOLDER"]) / "modelo_v1.joblib").is_file()


def test_detalle_de_modelo_en_entrenamiento_no_falla(app):
    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        m = ModeloML(version=2, estado="entrenando")
        db.session.add(m)
        db.session.commit()
        mid = m.id
    r = admin.get(f"/admin/modelos/{mid}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/modelos")
    assert admin.get("/admin/modelos").status_code == 200  # la lista tolera filas sin métricas


def test_importar_datos_reales_reemplaza_los_sinteticos(app):
    """Con suficientes registros reales, se puede dejar el modelo 100 % con datos reales."""
    from app.ml.datagen import generar_dataset

    admin = cliente_con_rol(app, "administrador")
    with app.app_context():
        services.cargar_sintetico(200, semilla=2)
    df = generar_dataset(80, semilla=77)
    csv_real = df.to_csv(index=False)
    html = subir_csv(admin, csv_real, reemplazar=True).get_data(as_text=True)
    assert "80 registros nuevos" in html and "Se eliminaron 200 registros sintéticos" in html
    with app.app_context():
        assert services.composicion_dataset() == {"csv": 80}
        m = services.lanzar_entrenamiento(None, sincrono=True)
        assert m.estado == "listo" and m.origen_datos == "real"
        assert m.composicion == {"csv": 80}
