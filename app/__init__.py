"""Arequipa House ML · fábrica de la aplicación Flask."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template
from flask_login import current_user

from .config import Config, INSTANCE_DIR
from .extensions import csrf, db, login_manager


def create_app(config_object=None) -> Flask:
    cfg = config_object or Config
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=False)
    app.config.from_object(cfg)
    Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)

    if app.config["APP_ENV"] == "production" and app.config["SECRET_KEY"].startswith("dev-insecure"):
        raise RuntimeError("Defina la variable de entorno SECRET_KEY en producción.")

    if app.config["APP_ENV"] == "production":  # detrás del proxy de Render/Heroku/nginx
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .blueprints import admin, auth, interaccion, main, propiedades, tasacion, vendedor

    for modulo in (main, auth, tasacion, propiedades, vendedor, interaccion, admin):
        app.register_blueprint(modulo.bp)

    _registrar_filtros(app)
    _registrar_contexto(app)
    _registrar_errores(app)
    _registrar_cabeceras(app)

    from .cli import registrar_comandos

    registrar_comandos(app)

    if app.config["AUTO_BOOTSTRAP"] and not app.config.get("TESTING"):
        from .bootstrap import bootstrap

        bootstrap(app)
    return app


def _registrar_filtros(app: Flask) -> None:
    from .utils import a_lima

    @app.template_filter("soles")
    def soles(valor, decimales=0):
        if valor is None:
            return "—"
        return f"S/ {valor:,.{decimales}f}"

    @app.template_filter("num")
    def num(valor, decimales=0):
        return f"{valor:,.{decimales}f}"

    @app.template_filter("m2")
    def m2(valor):
        return f"{valor:g} m²"

    @app.template_filter("fecha")
    def fecha(valor, hora=True):
        if not valor:
            return "—"
        valor = a_lima(valor)
        return valor.strftime("%d/%m/%Y %H:%M" if hora else "%d/%m/%Y")

    @app.template_filter("fecha_local")  # para valores ya expresados en hora de Lima
    def fecha_local(valor):
        return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"

    @app.template_filter("pct")
    def pct(valor, decimales=1):
        return f"{valor * 100:.{decimales}f} %"

    @app.template_filter("signo_soles")
    def signo_soles(valor):
        return f"{'+' if valor >= 0 else '−'} S/ {abs(valor):,.0f}"


def _registrar_contexto(app: Flask) -> None:
    from sqlalchemy import or_

    from .ml.constants import ACABADOS, DISTRITO_NOMBRES, ESTADOS, TIPOS
    from .models import Mensaje, Propiedad, Visita

    @app.context_processor
    def globales():
        datos = {
            "TIPOS": TIPOS,
            "DISTRITOS": DISTRITO_NOMBRES,
            "ESTADOS": ESTADOS,
            "ACABADOS": ACABADOS,
            "ENTORNO": app.config["APP_ENV"],
        }
        avisos = {"mensajes": 0, "visitas": 0, "moderacion": 0}
        if current_user.is_authenticated:
            avisos["mensajes"] = (
                Mensaje.query.join(Propiedad, Mensaje.propiedad_id == Propiedad.id)
                .filter(
                    Mensaje.leido.is_(False),
                    Mensaje.autor_id != current_user.id,
                    or_(Mensaje.comprador_id == current_user.id, Propiedad.vendedor_id == current_user.id),
                )
                .count()
            )
            if current_user.rol == "vendedor":
                avisos["visitas"] = (
                    Visita.query.join(Propiedad, Visita.propiedad_id == Propiedad.id)
                    .filter(Propiedad.vendedor_id == current_user.id, Visita.estado == "pendiente")
                    .count()
                )
            elif current_user.rol == "administrador":
                avisos["moderacion"] = Propiedad.query.filter_by(estado="pendiente").count()
        datos["avisos"] = avisos
        return datos


def _registrar_errores(app: Flask) -> None:
    def respuesta(codigo, titulo, detalle):
        return render_template("errors/error.html", codigo=codigo, titulo=titulo, detalle=detalle), codigo

    @app.errorhandler(403)
    def e403(_e):
        return respuesta(403, "Acceso denegado", "No tienes permiso para ver esta página.")

    @app.errorhandler(404)
    def e404(_e):
        return respuesta(404, "Página no encontrada", "El enlace no existe o la publicación ya no está disponible.")

    @app.errorhandler(413)
    def e413(_e):
        return respuesta(413, "Archivo demasiado grande", "Las fotos enviadas superan el tamaño máximo permitido.")

    @app.errorhandler(400)
    def e400(e):
        return respuesta(400, "Solicitud no válida", getattr(e, "description", "La solicitud no pudo procesarse."))

    @app.errorhandler(500)
    def e500(_e):
        db.session.rollback()
        return respuesta(500, "Error del servidor", "Ocurrió un problema inesperado. Intenta nuevamente.")


def _registrar_cabeceras(app: Flask) -> None:
    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp
