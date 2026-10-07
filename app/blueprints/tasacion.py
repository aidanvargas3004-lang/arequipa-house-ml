"""Tasación con Machine Learning, historial de estimaciones y API interna."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import services
from ..extensions import db
from ..forms import desde_formulario, precargado
from ..ml.schema import limpiar_vivienda
from ..models import Propiedad, Tasacion

bp = Blueprint("tasacion", __name__)


@bp.route("/tasar", methods=["GET", "POST"])
@login_required
def tasar():
    if request.method == "POST":
        valores = desde_formulario(request.form)
        datos, errores = limpiar_vivienda(request.form)
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("tasacion/tasar.html", v=valores), 422
        est = services.estimar(datos)
        t = services.registrar_tasacion(current_user.id, datos, est)
        return redirect(url_for("tasacion.detalle", tasacion_id=t.id))
    return render_template("tasacion/tasar.html", v=precargado(request.args))


@bp.route("/tasacion/<int:tasacion_id>")
@login_required
def detalle(tasacion_id):
    t = db.get_or_404(Tasacion, tasacion_id)
    if t.usuario_id != current_user.id and not current_user.es_admin:
        abort(403)
    d = t.datos
    similares = (
        Propiedad.query.filter_by(estado="aprobada", distrito=d.get("distrito"), tipo=d.get("tipo"))
        .order_by(db.func.abs(Propiedad.area_construida - d.get("area_construida", 0)))
        .limit(3)
        .all()
    )
    return render_template("tasacion/resultado.html", t=t, similares=similares)


@bp.route("/historial")
@login_required
def historial():
    q = Tasacion.query.filter_by(usuario_id=current_user.id)
    pagina = request.args.get("pagina", 1, type=int)
    pag = q.order_by(Tasacion.creado_en.desc()).paginate(page=pagina, per_page=10, error_out=False)
    return render_template("tasacion/historial.html", pag=pag)


@bp.route("/tasacion/<int:tasacion_id>/eliminar", methods=["POST"])
@login_required
def eliminar(tasacion_id):
    t = db.get_or_404(Tasacion, tasacion_id)
    if t.usuario_id != current_user.id and not current_user.es_admin:
        abort(403)
    db.session.delete(t)
    db.session.commit()
    flash("Tasación eliminada del historial.", "ok")
    return redirect(url_for("tasacion.historial"))


@bp.route("/api/tasar", methods=["POST"])
@login_required
def api_tasar():
    """Estimación rápida (no se guarda en el historial). Usada al publicar una vivienda."""
    datos, errores = limpiar_vivienda(request.form)
    if errores:
        return jsonify(ok=False, errores=errores), 422
    est = services.estimar(datos)
    return jsonify(
        ok=True,
        precio=est["precio"],
        precio_min=est["precio_min"],
        precio_max=est["precio_max"],
        precio_m2=est["precio_m2"],
        modelo=f"v{est['modelo'].version} · {est['modelo'].algoritmo_nombre}",
        factores=[
            {"etiqueta": f["etiqueta"], "valor": f["valor"], "impacto": f["impacto"]} for f in est["factores"][:5]
        ],
    )
