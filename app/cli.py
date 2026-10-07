"""Comandos de línea: ``flask --app wsgi <comando>``."""
import click

from . import services
from .bootstrap import bootstrap, crear_usuario, sembrar_demo
from .extensions import db
from .models import Usuario


def registrar_comandos(app):
    @app.cli.command("bootstrap")
    def cmd_bootstrap():
        """Crea tablas, parámetros, administrador, dataset y modelo inicial."""
        bootstrap(app)
        click.echo("Listo.")

    @app.cli.command("seed-demo")
    def cmd_seed():
        """Crea usuarios y publicaciones de demostración."""
        sembrar_demo()
        click.echo("Datos de demostración creados.")

    @app.cli.command("train")
    @click.option("--activar/--no-activar", default=True, help="Activar el modelo al terminar.")
    def cmd_train(activar):
        """Entrena una nueva versión del modelo con el dataset actual."""
        m = services.lanzar_entrenamiento(None, activar=activar, sincrono=True)
        if m.estado == "listo":
            g = m.metricas_ganador
            click.echo(f"Modelo v{m.version} ({m.algoritmo_nombre}) · MAE S/ {g['mae']:,.0f} · RMSE S/ {g['rmse']:,.0f} · R² {g['r2']}")
        else:
            raise click.ClickException(m.error or "Error desconocido")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.password_option()
    @click.option("--nombre", default="Administrador")
    def cmd_admin(email, password, nombre):
        """Crea un usuario administrador."""
        if Usuario.query.filter_by(email=email.lower()).first():
            raise click.ClickException("Ese correo ya existe.")
        crear_usuario(nombre, email, "administrador", password)
        db.session.commit()
        click.echo("Administrador creado.")
