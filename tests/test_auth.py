from app.extensions import db
from app.models import Usuario

from .conftest import CLAVE, cliente_con_rol, crear_usuario, login


def registrar(client, **extra):
    data = {"nombre": "Nuevo Usuario", "email": "nuevo@test.pe", "telefono": "999111222", "rol": "comprador",
            "password": CLAVE, "password2": CLAVE, "acepta": "1"}
    data.update(extra)
    return client.post("/registro", data=data, follow_redirects=False)


def test_registro_y_login(client, app):
    r = registrar(client)
    assert r.status_code == 302
    with app.app_context():
        u = Usuario.query.filter_by(email="nuevo@test.pe").first()
        assert u and u.rol == "comprador" and u.password_hash != CLAVE
    assert client.get("/historial").status_code == 200
    client.post("/logout")
    assert client.get("/historial").status_code == 302


def test_registro_validaciones(client):
    for extra in ({"password": "corta1", "password2": "corta1"}, {"password": "sololetras", "password2": "sololetras"},
                  {"password2": "Otra12345"}, {"email": "no-es-correo"}, {"rol": "administrador"}, {"acepta": ""}):
        assert registrar(client, **extra).status_code == 200  # vuelve al formulario


def test_no_se_puede_registrar_administrador(client, app):
    registrar(client, rol="administrador", email="x@test.pe")
    with app.app_context():
        assert Usuario.query.filter_by(email="x@test.pe").first() is None


def test_correo_duplicado(client, app):
    crear_usuario(app, "comprador", "dup@test.pe")
    assert registrar(client, email="dup@test.pe").status_code == 200


def test_login_incorrecto_y_bloqueo(client, app):
    crear_usuario(app, "comprador", "a@test.pe")
    for _ in range(5):
        assert client.post("/login", data={"email": "a@test.pe", "password": "mala"}).status_code == 200
    r = login(client, "a@test.pe")  # clave correcta, pero cuenta bloqueada
    assert r.status_code == 200
    with app.app_context():
        u = Usuario.query.filter_by(email="a@test.pe").first()
        assert u.esta_bloqueado


def test_usuario_suspendido_no_entra(client, app):
    uid = crear_usuario(app, "comprador", "s@test.pe")
    with app.app_context():
        db.session.get(Usuario, uid).activo = False
        db.session.commit()
    assert login(client, "s@test.pe").status_code == 200


def test_redireccion_abierta_bloqueada(client, app):
    crear_usuario(app, "comprador", "r@test.pe")
    r = client.post("/login?next=//evil.com", data={"email": "r@test.pe", "password": CLAVE})
    assert r.status_code == 302 and "evil.com" not in r.headers["Location"]
    client.post("/logout")
    r = client.post("/login?next=/propiedades", data={"email": "r@test.pe", "password": CLAVE})
    assert r.headers["Location"].endswith("/propiedades")


def test_control_de_roles(app, client):
    assert client.get("/admin/").status_code == 302  # anónimo → login
    comprador = cliente_con_rol(app, "comprador")
    assert comprador.get("/admin/").status_code == 403
    assert comprador.get("/vendedor/publicar").status_code == 403
    vendedor = cliente_con_rol(app, "vendedor")
    assert vendedor.get("/admin/usuarios").status_code == 403
    admin = cliente_con_rol(app, "administrador")
    assert admin.get("/admin/").status_code == 200
    assert admin.get("/vendedor/publicar").status_code == 403  # el admin no publica


def test_perfil_cambio_de_clave(app):
    c = cliente_con_rol(app, "comprador")
    c.post("/perfil", data={"accion": "clave", "actual": "incorrecta1", "nueva": "Nueva12345", "nueva2": "Nueva12345"})
    assert login(app.test_client(), "comprador@test.pe", "Nueva12345").status_code == 200  # no cambió
    c.post("/perfil", data={"accion": "clave", "actual": CLAVE, "nueva": "Nueva12345", "nueva2": "Nueva12345"})
    assert login(app.test_client(), "comprador@test.pe", "Nueva12345").status_code == 302
