"""Mensajes entre comprador y vendedor, y solicitudes de visita."""
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import Mensaje, Propiedad, Usuario, Visita
from ..utils import ahora_lima, roles_required

bp = Blueprint("interaccion", __name__)

ACTIVAS = ("pendiente", "confirmada")


# ------------------------------------------------------------------- mensajes
@bp.route("/propiedades/<int:propiedad_id>/contactar", methods=["POST"])
@roles_required("comprador", "vendedor")
def contactar(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    if p.estado != "aprobada":
        abort(404)
    if p.vendedor_id == current_user.id:
        flash("No puedes enviarte mensajes a ti mismo.", "warning")
        return redirect(url_for("propiedades.detalle", propiedad_id=p.id))
    texto = request.form.get("contenido", "").strip()
    if not 5 <= len(texto) <= 1000:
        flash("Escribe un mensaje de entre 5 y 1000 caracteres.", "error")
        return redirect(url_for("propiedades.detalle", propiedad_id=p.id))
    db.session.add(Mensaje(propiedad_id=p.id, comprador_id=current_user.id, autor_id=current_user.id, contenido=texto))
    db.session.commit()
    flash("Mensaje enviado al vendedor.", "ok")
    return redirect(url_for("interaccion.conversacion", propiedad_id=p.id, comprador_id=current_user.id))


@bp.route("/mensajes")
@roles_required("comprador", "vendedor")
def mensajes():
    uid = current_user.id
    msgs = (
        Mensaje.query.join(Propiedad, Mensaje.propiedad_id == Propiedad.id)
        .filter(or_(Mensaje.comprador_id == uid, Propiedad.vendedor_id == uid))
        .order_by(Mensaje.creado_en.desc())
        .limit(500)
        .all()
    )
    conversaciones: dict = {}
    for m in msgs:
        c = conversaciones.setdefault(
            (m.propiedad_id, m.comprador_id), {"propiedad": m.propiedad, "comprador": m.comprador, "ultimo": m, "no_leidos": 0}
        )
        if not m.leido and m.autor_id != uid:
            c["no_leidos"] += 1
    return render_template("comprador/mensajes.html", conversaciones=list(conversaciones.values()))


@bp.route("/mensajes/<int:propiedad_id>/<int:comprador_id>", methods=["GET", "POST"])
@roles_required("comprador", "vendedor")
def conversacion(propiedad_id, comprador_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    if current_user.id not in (comprador_id, p.vendedor_id):
        abort(403)
    comprador = db.get_or_404(Usuario, comprador_id)
    if request.method == "POST":
        texto = request.form.get("contenido", "").strip()
        if not 1 <= len(texto) <= 1000:
            flash("El mensaje debe tener entre 1 y 1000 caracteres.", "error")
        else:
            db.session.add(Mensaje(propiedad_id=p.id, comprador_id=comprador_id, autor_id=current_user.id, contenido=texto))
            db.session.commit()
        return redirect(url_for("interaccion.conversacion", propiedad_id=p.id, comprador_id=comprador_id))
    msgs = Mensaje.query.filter_by(propiedad_id=p.id, comprador_id=comprador_id).order_by(Mensaje.creado_en).all()
    if not msgs:
        abort(404)
    for m in msgs:
        if m.autor_id != current_user.id and not m.leido:
            m.leido = True
    db.session.commit()
    otro = p.vendedor if current_user.id == comprador_id else comprador
    return render_template("comprador/conversacion.html", p=p, msgs=msgs, otro=otro)


# --------------------------------------------------------------------- visitas
def _parsear_fecha(valor: str):
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


@bp.route("/propiedades/<int:propiedad_id>/visita", methods=["POST"])
@roles_required("comprador", "vendedor")
def solicitar_visita(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    if p.estado != "aprobada":
        abort(404)
    destino = redirect(url_for("propiedades.detalle", propiedad_id=p.id))
    if p.vendedor_id == current_user.id:
        flash("No puedes solicitar una visita a tu propia vivienda.", "warning")
        return destino
    fecha = _parsear_fecha(request.form.get("fecha_hora", ""))
    modalidad = request.form.get("modalidad", "presencial")
    comentario = request.form.get("comentario", "").strip()[:400]
    ahora = ahora_lima()
    if modalidad not in ("presencial", "virtual"):
        flash("Elige una modalidad de visita válida.", "error")
    elif fecha is None:
        flash("Ingresa una fecha y hora válidas.", "error")
    elif fecha < ahora + timedelta(hours=2):
        flash("La visita debe programarse con al menos 2 horas de anticipación.", "error")
    elif fecha > ahora + timedelta(days=60):
        flash("Solo se pueden programar visitas dentro de los próximos 60 días.", "error")
    elif not 8 <= fecha.hour < 19:
        flash("El horario de visitas es de 8:00 a 19:00 (hora de Lima).", "error")
    elif Visita.query.filter(
        Visita.propiedad_id == p.id, Visita.comprador_id == current_user.id, Visita.estado.in_(ACTIVAS)
    ).first():
        flash("Ya tienes una visita activa para esta vivienda.", "warning")
    else:
        db.session.add(Visita(propiedad_id=p.id, comprador_id=current_user.id, fecha_hora=fecha.replace(second=0, microsecond=0),
                              modalidad=modalidad, comentario=comentario or None))
        db.session.commit()
        flash("Solicitud de visita enviada. El vendedor la confirmará pronto.", "ok")
        return redirect(url_for("interaccion.visitas"))
    return destino


@bp.route("/visitas")
@roles_required("comprador", "vendedor")
def visitas():
    uid = current_user.id
    mias = Visita.query.filter_by(comprador_id=uid).order_by(Visita.fecha_hora.desc()).all()
    recibidas = (
        Visita.query.join(Propiedad, Visita.propiedad_id == Propiedad.id)
        .filter(Propiedad.vendedor_id == uid)
        .order_by(Visita.fecha_hora.desc())
        .all()
    )
    return render_template("comprador/visitas.html", mias=mias, recibidas=recibidas)


@bp.route("/visitas/<int:visita_id>/responder", methods=["POST"])
@roles_required("vendedor")
def responder_visita(visita_id):
    v = db.get_or_404(Visita, visita_id)
    if v.propiedad.vendedor_id != current_user.id:
        abort(403)
    accion = request.form.get("accion")
    if v.estado != "pendiente":
        flash("Esa solicitud ya fue respondida.", "warning")
    elif accion not in ("confirmar", "rechazar"):
        abort(400)
    else:
        v.estado = "confirmada" if accion == "confirmar" else "rechazada"
        v.respuesta = request.form.get("respuesta", "").strip()[:300] or None
        db.session.commit()
        flash("Visita confirmada." if accion == "confirmar" else "Visita rechazada.", "ok")
    return redirect(url_for("interaccion.visitas"))


@bp.route("/visitas/<int:visita_id>/cancelar", methods=["POST"])
@roles_required("comprador", "vendedor")
def cancelar_visita(visita_id):
    v = db.get_or_404(Visita, visita_id)
    if v.comprador_id != current_user.id:
        abort(403)
    if v.estado in ACTIVAS:
        v.estado = "cancelada"
        db.session.commit()
        flash("Visita cancelada.", "ok")
    return redirect(url_for("interaccion.visitas"))
