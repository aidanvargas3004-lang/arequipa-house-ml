import io
import shutil

import pytest
from PIL import Image

from app import create_app, services
from app.config import TestConfig
from app.extensions import db
from app.ml.datagen import generar_dataset
from app.ml.pipeline import entrenar, guardar
from app.models import ModeloML, Usuario

CLAVE = "Clave12345"


@pytest.fixture(scope="session")
def modelo_compartido(tmp_path_factory):
    """Entrena una sola vez un modelo pequeño que reutilizan todas las pruebas."""
    carpeta = tmp_path_factory.mktemp("modelos")
    resultado = entrenar(generar_dataset(700, 11), semilla=42, minimo_filas=60)
    guardar(resultado["bundle"], carpeta / "modelo_v1.joblib")
    return carpeta, resultado["metricas"]


def _construir_app(tmp_path, modelo_compartido, config=TestConfig):
    origen, metricas = modelo_compartido
    carpeta = tmp_path / "modelos"  # copia propia: las pruebas pueden borrar archivos
    shutil.copytree(origen, carpeta)
    app = create_app(config)
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["MODELS_FOLDER"] = str(carpeta)
    with app.app_context():
        db.create_all()
        services.asegurar_parametros()
        db.session.add(
            ModeloML(
                version=1, algoritmo=metricas["ganador"], archivo="modelo_v1.joblib", estado="listo",
                activo=True, metricas=metricas, composicion={"sintetico": 700},
            )
        )
        db.session.commit()
        services.reiniciar_cache()
    return app


@pytest.fixture()
def app(tmp_path, modelo_compartido):
    app = _construir_app(tmp_path, modelo_compartido)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_csrf(tmp_path, modelo_compartido):
    class ConCsrf(TestConfig):
        WTF_CSRF_ENABLED = True

    app = _construir_app(tmp_path, modelo_compartido, ConCsrf)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def crear_usuario(app, rol="comprador", email=None, nombre="Usuario Prueba"):
    email = email or f"{rol}@test.pe"
    with app.app_context():
        u = Usuario(nombre=nombre, email=email, rol=rol, telefono="999888777")
        u.set_password(CLAVE)
        db.session.add(u)
        db.session.commit()
        return u.id


def login(client, email, clave=CLAVE):
    return client.post("/login", data={"email": email, "password": clave}, follow_redirects=False)


def cliente_con_rol(app, rol, email=None):
    email = email or f"{rol}@test.pe"
    crear_usuario(app, rol, email)
    c = app.test_client()
    r = login(c, email)
    assert r.status_code == 302
    return c


def png_bytes(color=(200, 100, 50), tam=(320, 240)):
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, "PNG")
    return buf.getvalue()


VIVIENDA = {
    "tipo": "Departamento", "distrito": "Cayma", "area_construida": "110", "area_terreno": "",
    "habitaciones": "3", "banos": "2", "pisos": "1", "antiguedad": "5",
    "estado_conservacion": "Bueno", "acabados": "Alta calidad", "cochera": "1",
    "ascensor": "1", "transporte_publico": "1",
}


def datos_publicacion(**extra):
    d = dict(VIVIENDA)
    d.update(
        titulo="Departamento moderno en Cayma", direccion="Av. Ejército 123, Cayma",
        descripcion="Departamento luminoso con excelente ubicación y acabados modernos.",
        precio="520000",
    )
    d.update(extra)
    return d


def publicar(client, **extra):
    data = datos_publicacion(**extra)
    data["fotos"] = (io.BytesIO(png_bytes()), "casa.png")
    return client.post("/vendedor/publicar", data=data, content_type="multipart/form-data", follow_redirects=False)
