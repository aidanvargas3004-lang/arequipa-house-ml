import io

from app.extensions import db
from app.models import DatasetRegistro, Propiedad

from .conftest import cliente_con_rol, datos_publicacion, png_bytes, publicar


def test_ciclo_publicacion_y_moderacion(app, client):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")

    assert publicar(v).status_code == 302
    with app.app_context():
        p = Propiedad.query.one()
        assert p.estado == "pendiente" and len(p.fotos) == 1
        pid = p.id

    # Aún no es público
    assert "Departamento moderno" not in client.get("/propiedades").get_data(as_text=True)
    assert client.get(f"/propiedades/{pid}").status_code == 404
    assert v.get(f"/propiedades/{pid}").status_code == 200  # el dueño sí la ve
    assert "Pendiente" in admin.get("/admin/publicaciones").get_data(as_text=True)

    # El administrador aprueba
    assert admin.post(f"/admin/publicaciones/{pid}/moderar", data={"accion": "aprobar"}).status_code == 302
    html = client.get("/propiedades").get_data(as_text=True)
    assert "Departamento moderno" in html
    det = client.get(f"/propiedades/{pid}").get_data(as_text=True)
    assert "Valoración del modelo" in det and "Inicia sesión" in det

    # Imagen servida y protegida contra path traversal
    with app.app_context():
        archivo = db.session.get(Propiedad, pid).fotos[0].archivo
    assert client.get(f"/media/{archivo}").status_code == 200
    assert client.get("/media/..%2f..%2fetc%2fpasswd").status_code == 404


def test_rechazo_requiere_motivo_y_se_muestra(app):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v)
    sin = admin.post("/admin/publicaciones/1/moderar", data={"accion": "rechazar", "motivo": ""})
    assert sin.status_code == 302
    with app.app_context():
        assert db.session.get(Propiedad, 1).estado == "pendiente"
    admin.post("/admin/publicaciones/1/moderar", data={"accion": "rechazar", "motivo": "Fotos borrosas"})
    assert "Fotos borrosas" in v.get("/vendedor/publicaciones").get_data(as_text=True)


def test_validaciones_de_publicacion(app):
    v = cliente_con_rol(app, "vendedor")
    sin_foto = v.post("/vendedor/publicar", data=datos_publicacion(), content_type="multipart/form-data")
    assert sin_foto.status_code == 422
    falsa = datos_publicacion()
    falsa["fotos"] = (io.BytesIO(b"esto no es una imagen"), "virus.png")
    assert v.post("/vendedor/publicar", data=falsa, content_type="multipart/form-data").status_code == 422
    mala = datos_publicacion(precio="100", titulo="x")
    mala["fotos"] = (io.BytesIO(png_bytes()), "a.png")
    assert v.post("/vendedor/publicar", data=mala, content_type="multipart/form-data").status_code == 422
    with app.app_context():
        assert Propiedad.query.count() == 0


def test_solo_el_dueno_edita_y_elimina(app):
    v1 = cliente_con_rol(app, "vendedor", "v1@test.pe")
    v2 = cliente_con_rol(app, "vendedor", "v2@test.pe")
    publicar(v1)
    assert v2.get("/vendedor/publicaciones/1/editar").status_code == 403
    assert v2.post("/vendedor/publicaciones/1/eliminar").status_code == 403
    r = v1.post("/vendedor/publicaciones/1/editar", data=datos_publicacion(precio="600000", titulo="Título editado OK"))
    assert r.status_code == 302
    with app.app_context():
        p = db.session.get(Propiedad, 1)
        assert p.precio == 600000 and p.titulo == "Título editado OK"
    assert v1.post("/vendedor/publicaciones/1/eliminar").status_code == 302
    with app.app_context():
        assert db.session.get(Propiedad, 1) is None


def test_editar_aprobada_vuelve_a_revision(app):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v)
    admin.post("/admin/publicaciones/1/moderar", data={"accion": "aprobar"})
    v.post("/vendedor/publicaciones/1/editar", data=datos_publicacion(precio="610000"))
    with app.app_context():
        assert db.session.get(Propiedad, 1).estado == "pendiente"


def test_ultima_foto_no_se_elimina(app):
    v = cliente_con_rol(app, "vendedor")
    publicar(v)
    v.post("/vendedor/fotos/1/eliminar")
    with app.app_context():
        assert len(db.session.get(Propiedad, 1).fotos) == 1


def test_marcar_vendida_aporta_al_dataset(app):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v)
    admin.post("/admin/publicaciones/1/moderar", data={"accion": "aprobar"})
    r = v.post("/vendedor/publicaciones/1/vendida", data={"precio_final": "500000", "aportar_dataset": "1"})
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Propiedad, 1).estado == "vendida"
        reg = DatasetRegistro.query.filter_by(origen="venta").one()
        assert reg.precio == 500000 and reg.distrito == "Cayma"


def test_catalogo_filtros_y_orden(app, client):
    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v, titulo="Depa Cayma barato", precio="300000")
    publicar(v, titulo="Casa Yanahuara cara", precio="900000", tipo="Casa", distrito="Yanahuara", area_terreno="200", pisos="2", area_construida="180")
    for i in (1, 2):
        admin.post(f"/admin/publicaciones/{i}/moderar", data={"accion": "aprobar"})
    todo = client.get("/propiedades").get_data(as_text=True)
    assert "Depa Cayma barato" in todo and "Casa Yanahuara cara" in todo
    solo = client.get("/propiedades?distrito=Yanahuara").get_data(as_text=True)
    assert "Casa Yanahuara cara" in solo and "Depa Cayma barato" not in solo
    rango = client.get("/propiedades?precio_max=400000").get_data(as_text=True)
    assert "Depa Cayma barato" in rango and "Casa Yanahuara cara" not in rango
    orden = client.get("/propiedades?orden=precio_desc").get_data(as_text=True)
    assert orden.index("Casa Yanahuara cara") < orden.index("Depa Cayma barato")
    # entradas hostiles no rompen la búsqueda
    assert client.get("/propiedades?precio_min=abc&habitaciones=;drop&orden=zzz&pagina=-3").status_code == 200
    assert client.get("/propiedades?q=%27%20OR%201%3D1--").status_code == 200
