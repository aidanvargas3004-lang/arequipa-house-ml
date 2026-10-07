from datetime import timedelta

from app.extensions import db
from app.models import Favorito, Mensaje, Visita
from app.utils import ahora_lima

from .conftest import cliente_con_rol, publicar


def preparar(app):
    vend = cliente_con_rol(app, "vendedor")
    admin = cliente_con_rol(app, "administrador")
    comp = cliente_con_rol(app, "comprador")
    publicar(vend)
    publicar(vend, titulo="Segunda vivienda en venta", distrito="Paucarpata")
    for i in (1, 2):
        admin.post(f"/admin/publicaciones/{i}/moderar", data={"accion": "aprobar"})
    return vend, comp, admin


def test_favoritos(app):
    _, comp, _ = preparar(app)
    comp.post("/propiedades/1/favorito")
    with app.app_context():
        assert Favorito.query.count() == 1
    assert "Departamento moderno" in comp.get("/favoritos").get_data(as_text=True)
    comp.post("/propiedades/1/favorito")  # alternar
    with app.app_context():
        assert Favorito.query.count() == 0


def test_comparador_maximo_cuatro(app, client):
    vend, _, admin = preparar(app)
    for _ in range(3):
        publicar(vend)
    for i in (3, 4, 5):
        admin.post(f"/admin/publicaciones/{i}/moderar", data={"accion": "aprobar"})
    for i in range(1, 6):
        client.post(f"/comparar/agregar/{i}")
    html = client.get("/comparar").get_data(as_text=True)
    assert html.count("Quitar") == 4
    assert "Mejor" in html and "Valor estimado" in html
    client.post("/comparar/quitar/1")
    assert client.get("/comparar").get_data(as_text=True).count("Quitar") == 3
    client.post("/comparar/vaciar")
    assert "vacío" in client.get("/comparar").get_data(as_text=True)


def test_mensajes_entre_comprador_y_vendedor(app):
    vend, comp, _ = preparar(app)
    r = comp.post("/propiedades/1/contactar", data={"contenido": "Hola, ¿sigue disponible?"})
    assert r.status_code == 302
    comp.post("/propiedades/1/contactar", data={"contenido": "x"})  # demasiado corto
    with app.app_context():
        assert Mensaje.query.count() == 1
        cid = Mensaje.query.one().comprador_id
    assert "1 nuevo" in vend.get("/mensajes").get_data(as_text=True)
    hilo = vend.get(f"/mensajes/1/{cid}")
    assert hilo.status_code == 200 and "sigue disponible" in hilo.get_data(as_text=True)
    vend.post(f"/mensajes/1/{cid}", data={"contenido": "Sí, claro."})
    with app.app_context():
        assert Mensaje.query.filter_by(leido=False).count() == 1  # la respuesta aún no fue leída por el comprador
    assert "Sí, claro." in comp.get(f"/mensajes/1/{cid}").get_data(as_text=True)
    with app.app_context():
        assert Mensaje.query.filter_by(leido=False).count() == 0  # al abrir el hilo queda leída


def test_conversacion_ajena_prohibida(app):
    vend, comp, _ = preparar(app)
    comp.post("/propiedades/1/contactar", data={"contenido": "Hola, me interesa"})
    otro = cliente_con_rol(app, "comprador", "otro@test.pe")
    with app.app_context():
        cid = Mensaje.query.one().comprador_id
    assert otro.get(f"/mensajes/1/{cid}").status_code == 403
    # el dueño no puede contactarse a sí mismo
    vend.post("/propiedades/1/contactar", data={"contenido": "Hola yo mismo"})
    with app.app_context():
        assert Mensaje.query.count() == 1


def manana(hora=11):
    return (ahora_lima() + timedelta(days=2)).replace(hour=hora, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def test_visitas_validaciones_y_flujo(app):
    vend, comp, _ = preparar(app)
    pasada = (ahora_lima() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    for malo in ({"fecha_hora": pasada}, {"fecha_hora": manana(23)}, {"fecha_hora": "no-fecha"}, {"fecha_hora": manana(), "modalidad": "hackeo"}):
        comp.post("/propiedades/1/visita", data={"modalidad": "presencial", **malo})
    with app.app_context():
        assert Visita.query.count() == 0
    ok = comp.post("/propiedades/1/visita", data={"fecha_hora": manana(), "modalidad": "virtual", "comentario": "Por la mañana"})
    assert ok.status_code == 302
    comp.post("/propiedades/1/visita", data={"fecha_hora": manana(15), "modalidad": "presencial"})  # duplicada activa
    with app.app_context():
        assert Visita.query.count() == 1
        vid = Visita.query.one().id
    assert "Por la mañana" in vend.get("/visitas").get_data(as_text=True)
    assert comp.post(f"/visitas/{vid}/responder", data={"accion": "confirmar"}).status_code == 403  # el comprador no confirma
    vend.post(f"/visitas/{vid}/responder", data={"accion": "confirmar", "respuesta": "Los espero"})
    with app.app_context():
        v = db.session.get(Visita, vid)
        assert v.estado == "confirmada" and v.respuesta == "Los espero"
    comp.post(f"/visitas/{vid}/cancelar")
    with app.app_context():
        assert db.session.get(Visita, vid).estado == "cancelada"


def test_admin_no_usa_funciones_de_comprador(app):
    _, _, admin = preparar(app)
    assert admin.post("/propiedades/1/favorito").status_code == 403
    assert admin.post("/propiedades/1/contactar", data={"contenido": "hola hola"}).status_code == 403
