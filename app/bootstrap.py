"""Arranque inicial: tablas, parámetros, administrador, dataset, modelo y datos demo."""
from __future__ import annotations

import io
import random
import secrets
from datetime import timedelta

from flask import current_app
from PIL import Image, ImageDraw
from sqlalchemy.exc import IntegrityError

from . import services
from .extensions import db
from .ml.datagen import generar_dataset
from .models import Favorito, Foto, Mensaje, Propiedad, Usuario, Visita, ahora
from .utils import ahora_lima, guardar_imagen_bytes

DEMO_CLAVE = "Demo12345"
DEMO_USUARIOS = [
    ("Carla Quispe (vendedora demo)", "vendedor@demo.pe", "vendedor", "959 111 222"),
    ("Luis Mamani (vendedor demo)", "vendedor2@demo.pe", "vendedor", "959 333 444"),
    ("Ana Valdivia (compradora demo)", "comprador@demo.pe", "comprador", "959 555 666"),
]


def bootstrap(app) -> None:
    """Idempotente: puede ejecutarse en cada arranque."""
    with app.app_context():
        db.create_all()
        services.asegurar_parametros()
        _crear_admin()
        services.asegurar_modelo()
        if app.config["SEED_DEMO"]:
            sembrar_demo()


def _crear_admin() -> None:
    if Usuario.query.filter_by(rol="administrador").first():
        return
    cfg = current_app.config
    clave = cfg["ADMIN_PASSWORD"]
    generada = False
    if not clave:
        if cfg["APP_ENV"] == "production":
            clave, generada = secrets.token_urlsafe(12), True
        else:
            clave = "Admin12345"
    admin = Usuario(nombre="Administrador", email=cfg["ADMIN_EMAIL"].lower(), rol="administrador")
    admin.set_password(clave)
    db.session.add(admin)
    try:
        db.session.commit()
    except IntegrityError:  # otro proceso lo creó primero
        db.session.rollback()
        return
    if generada or cfg["APP_ENV"] != "production":
        current_app.logger.warning(
            "Administrador creado → usuario: %s  clave: %s  (cámbiela desde Mi perfil)", admin.email, clave
        )


def crear_usuario(nombre, email, rol, clave, telefono=None) -> Usuario:
    u = Usuario(nombre=nombre, email=email.lower(), rol=rol, telefono=telefono)
    u.set_password(clave)
    db.session.add(u)
    db.session.flush()
    return u


# --------------------------------------------------------------------- demo
def imagen_demo(tipo: str, semilla: int) -> bytes:
    """Ilustración sencilla de una vivienda (para la demostración)."""
    rnd = random.Random(semilla)
    w, h = 960, 640
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(125 + 75 * t), int(175 + 55 * t), int(232 + 15 * t)))
    d.polygon([(0, 430), (180, 330), (330, 410), (520, 300), (760, 420), (w, 360), (w, 480), (0, 480)], fill=(150, 160, 175))
    d.rectangle([0, 480, w, h], fill=(96, 152, 98))
    paredes = [(236, 214, 190), (246, 236, 214), (210, 224, 235), (240, 205, 190), (225, 235, 205)]
    techos = [(150, 70, 55), (90, 90, 105), (120, 80, 60), (70, 100, 120)]
    pared, techo = rnd.choice(paredes), rnd.choice(techos)
    ventana = (120, 175, 215)

    if tipo == "Departamento":
        d.rectangle([300, 70, 660, 500], fill=pared, outline=(80, 80, 80), width=3)
        for fila in range(6):
            for col in range(4):
                x, y = 330 + col * 82, 100 + fila * 62
                d.rectangle([x, y, x + 52, y + 40], fill=(255, 226, 140) if rnd.random() < 0.3 else ventana, outline=(70, 70, 70))
        d.rectangle([450, 440, 510, 500], fill=(90, 60, 40))
    elif tipo == "Dúplex":
        d.rectangle([250, 220, 710, 500], fill=pared, outline=(80, 80, 80), width=3)
        d.rectangle([235, 200, 725, 232], fill=techo)
        for fila in range(2):
            for col in range(4):
                x, y = 285 + col * 106, 250 + fila * 120
                d.rectangle([x, y, x + 64, y + 66], fill=ventana, outline=(70, 70, 70), width=2)
        d.rectangle([450, 420, 510, 500], fill=(90, 60, 40))
    else:
        d.rectangle([240, 300, 720, 500], fill=pared, outline=(80, 80, 80), width=3)
        d.polygon([(205, 304), (480, 160), (755, 304)], fill=techo)
        for x in (290, 560):
            d.rectangle([x, 340, x + 100, 420], fill=ventana, outline=(70, 70, 70), width=2)
        d.rectangle([440, 380, 520, 500], fill=(90, 60, 40))
    for x in (110, 840):
        d.rectangle([x, 400, x + 14, 490], fill=(100, 70, 45))
        d.ellipse([x - 44, 320, x + 58, 430], fill=(60, 130, 70))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


_CALLES = ["Av. Ejército", "Calle Mercaderes", "Av. Parra", "Calle Bolívar", "Av. Dolores", "Calle Jerusalén",
           "Av. Goyeneche", "Calle Ayacucho", "Av. Kennedy", "Calle Los Cedros"]


def _descripcion(f: dict) -> str:
    extras = [t for t, k in (("jardín", "jardin"), ("piscina", "piscina"), ("ascensor", "ascensor"), ("seguridad", "seguridad")) if f[k]]
    texto = (
        f"{f['tipo']} de {f['area_construida']:g} m² construidos"
        + (f" sobre {f['area_terreno']:g} m² de terreno" if f["tipo"] != "Departamento" else "")
        + f", con {f['habitaciones']} habitaciones y {f['banos']} baño{'s' if f['banos'] != 1 else ''}. "
        f"Acabados de calidad {f['acabados'].lower()}, en estado {f['estado_conservacion'].lower()} "
        + ("(a estrenar)." if f["antiguedad"] == 0 else f"({f['antiguedad']} años de antigüedad).")
    )
    if f["cochera"]:
        texto += f" Cuenta con {f['cochera']} cochera(s)."
    if extras:
        texto += " Incluye " + ", ".join(extras) + "."
    cerca = [t for t, k in (("colegios", "cerca_colegios"), ("hospitales", "cerca_hospitales"),
                            ("centros comerciales", "cerca_comercial"), ("transporte público", "transporte_publico")) if f[k]]
    if cerca:
        texto += " Cerca de " + ", ".join(cerca) + "."
    return texto + " (Publicación de demostración.)"


def sembrar_demo() -> None:
    """Crea usuarios y publicaciones de demostración (solo si aún no existen)."""
    if Usuario.query.filter_by(email="vendedor@demo.pe").first():
        return
    rnd = random.Random(2026)
    usuarios = {email: crear_usuario(n, email, rol, DEMO_CLAVE, tel) for n, email, rol, tel in DEMO_USUARIOS}
    vendedores = [usuarios["vendedor@demo.pe"], usuarios["vendedor2@demo.pe"]]
    comprador = usuarios["comprador@demo.pe"]

    df = generar_dataset(60, semilla=2024)
    estados = ["aprobada"] * 24 + ["pendiente"] * 3 + ["rechazada"]
    propiedades = []
    for i, (fila, estado) in enumerate(zip(df.to_dict("records"), estados)):
        fila = {k: (v.item() if hasattr(v, "item") else v) for k, v in fila.items()}
        precio = round(fila["precio"] * rnd.uniform(0.86, 1.16) / 1000) * 1000
        p = Propiedad(
            vendedor=vendedores[i % 2],
            titulo=f"{fila['tipo']} de {fila['habitaciones']} dormitorios en {fila['distrito']}",
            descripcion=_descripcion(fila),
            direccion=f"{rnd.choice(_CALLES)} {rnd.randint(100, 1900)}, {fila['distrito']}",
            precio=precio,
            estado=estado,
            motivo_rechazo="Faltan fotos que muestren el interior de la vivienda." if estado == "rechazada" else None,
            **{k: fila[k] for k in Propiedad.CAMPOS_MODELO},
        )
        for c in ("jardin", "piscina", "ascensor", "seguridad", "cerca_colegios", "cerca_hospitales",
                  "cerca_comercial", "transporte_publico"):
            setattr(p, c, bool(fila[c]))
        db.session.add(p)
        db.session.flush()
        for n in range(2):
            p.fotos.append(Foto(archivo=guardar_imagen_bytes(imagen_demo(p.tipo, i * 10 + n)), orden=n))
        propiedades.append(p)

    db.session.flush()
    aprobadas = [p for p in propiedades if p.estado == "aprobada"]
    for p in aprobadas[:3]:
        db.session.add(Favorito(usuario_id=comprador.id, propiedad_id=p.id))

    p0 = aprobadas[0]
    db.session.add_all([
        Mensaje(propiedad_id=p0.id, comprador_id=comprador.id, autor_id=comprador.id, leido=True,
                contenido="Hola, me interesa la propiedad. ¿Sigue disponible y es negociable el precio?"),
        Mensaje(propiedad_id=p0.id, comprador_id=comprador.id, autor_id=p0.vendedor_id, leido=False,
                contenido="¡Hola! Sí, sigue disponible. Podemos conversar el precio en una visita."),
        Visita(propiedad_id=aprobadas[1].id, comprador_id=comprador.id, modalidad="presencial",
               fecha_hora=(ahora_lima() + timedelta(days=3)).replace(hour=11, minute=0, second=0, microsecond=0),
               comentario="Quisiera conocer la propiedad por la mañana.", estado="pendiente"),
    ])
    db.session.commit()

    try:  # una tasación de ejemplo en el historial del comprador
        datos = aprobadas[2].datos_modelo()
        est = services.estimar(datos)
        services.registrar_tasacion(comprador.id, datos, est)
    except Exception:  # noqa: BLE001 - la demo no debe impedir el arranque
        db.session.rollback()
    current_app.logger.warning("Datos de demostración creados (clave de los usuarios demo: %s)", DEMO_CLAVE)
