"""Páginas generales: inicio, archivos subidos, información legal y salud."""
from flask import Blueprint, abort, jsonify, render_template, send_from_directory
from pathlib import Path

from ..extensions import db
from ..models import Propiedad
from ..utils import carpeta_subidas

bp = Blueprint("main", __name__)


@bp.route("/")
def inicio():
    destacadas = (
        Propiedad.query.filter_by(estado="aprobada").order_by(Propiedad.creado_en.desc()).limit(6).all()
    )
    total = Propiedad.query.filter_by(estado="aprobada").count()
    return render_template("index.html", destacadas=destacadas, total=total)


@bp.route("/media/<path:nombre>")
def media(nombre):
    # Solo archivos de la carpeta de subidas (sin subdirectorios).
    if Path(nombre).name != nombre:
        abort(404)
    return send_from_directory(carpeta_subidas(), nombre, max_age=60 * 60 * 24 * 7)


@bp.route("/privacidad")
def privacidad():
    return render_template("legal.html", pagina="privacidad")


@bp.route("/terminos")
def terminos():
    return render_template("legal.html", pagina="terminos")


@bp.route("/health")
def health():
    db.session.execute(db.text("SELECT 1"))
    return jsonify(estado="ok")
