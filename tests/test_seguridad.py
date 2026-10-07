from .conftest import CLAVE, crear_usuario, login


def test_csrf_activo_rechaza_posts_sin_token(app_csrf):
    c = app_csrf.test_client()
    crear_usuario(app_csrf, "comprador", "c@test.pe")
    assert c.post("/login", data={"email": "c@test.pe", "password": CLAVE}).status_code == 400
    assert c.post("/registro", data={}).status_code == 400
    # el formulario trae el token
    html = c.get("/login").get_data(as_text=True)
    assert 'name="csrf_token"' in html


def test_cabeceras_de_seguridad(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_salud_y_paginas_publicas(client):
    assert client.get("/health").get_json() == {"estado": "ok"}
    for ruta in ("/", "/propiedades", "/login", "/registro", "/privacidad", "/terminos", "/comparar"):
        assert client.get(ruta).status_code == 200, ruta
    assert client.get("/no-existe").status_code == 404


def test_xss_en_publicacion_se_escapa(app, client):
    from .conftest import cliente_con_rol, publicar

    v = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    publicar(v, titulo="<script>alert(1)</script> Depto", descripcion="<img src=x onerror=alert(1)> descripción larga de prueba")
    admin.post("/admin/publicaciones/1/moderar", data={"accion": "aprobar"})
    html = client.get("/propiedades/1").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html
