"""Gestión de publicaciones por parte del vendedor."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import services
from ..extensions import db
from ..forms import desde_formulario, desde_propiedad, precargado
from ..ml.constants import BOOLEANAS
from ..ml.schema import limpiar_vivienda
from ..models import Foto, Propiedad
from ..utils import borrar_archivo_foto, guardar_foto, roles_required

bp = Blueprint("vendedor", __name__, url_prefix="/vendedor")


def _propia(propiedad_id) -> Propiedad:
    p = db.get_or_404(Propiedad, propiedad_id)
    if p.vendedor_id != current_user.id:
        abort(403)
    return p


def _aplicar(p: Propiedad, datos: dict) -> None:
    for campo in Propiedad.CAMPOS_MODELO:
        valor = datos[campo]
        setattr(p, campo, bool(valor) if campo in BOOLEANAS else valor)


def _validar_textos(form) -> tuple[dict, list[str]]:
    textos = {
        "titulo": form.get("titulo", "").strip(),
        "descripcion": form.get("descripcion", "").strip(),
        "direccion": form.get("direccion", "").strip(),
    }
    errores = []
    if not 5 <= len(textos["titulo"]) <= 160:
        errores.append("El título debe tener entre 5 y 160 caracteres.")
    if len(textos["descripcion"]) < 20:
        errores.append("Describe la vivienda con al menos 20 caracteres.")
    if len(textos["descripcion"]) > 3000:
        errores.append("La descripción no puede superar los 3000 caracteres.")
    if not 5 <= len(textos["direccion"]) <= 200:
        errores.append("Ingresa la dirección o referencia (5 a 200 caracteres).")
    return textos, errores


def _guardar_fotos(p: Propiedad, archivos) -> list[str]:
    """Guarda las fotos válidas y devuelve los errores encontrados."""
    errores = []
    cupo = current_app.config["MAX_PHOTOS_PER_LISTING"] - len(p.fotos)
    archivos = [a for a in archivos if a and a.filename]
    if len(archivos) > cupo:
        errores.append(f"Solo puedes tener {current_app.config['MAX_PHOTOS_PER_LISTING']} fotos por publicación.")
        archivos = archivos[: max(cupo, 0)]
    for a in archivos:
        try:
            nombre = guardar_foto(a)
        except ValueError as e:
            errores.append(f"{a.filename}: {e}")
            continue
        p.fotos.append(Foto(archivo=nombre, orden=len(p.fotos)))
    return errores


@bp.route("/publicaciones")
@roles_required("vendedor")
def mis_publicaciones():
    props = Propiedad.query.filter_by(vendedor_id=current_user.id).order_by(Propiedad.creado_en.desc()).all()
    cuenta = {}
    for p in props:
        cuenta[p.estado] = cuenta.get(p.estado, 0) + 1
    return render_template("vendedor/lista.html", props=props, cuenta=cuenta)


@bp.route("/publicar", methods=["GET", "POST"])
@roles_required("vendedor")
def publicar():
    extra = {"titulo": "", "descripcion": "", "direccion": "", "precio": ""}
    if request.method == "POST":
        valores = desde_formulario(request.form)
        extra = {k: request.form.get(k, "").strip() for k in extra}
        datos, errores = limpiar_vivienda(request.form, exigir_precio=True)
        textos, err_textos = _validar_textos(request.form)
        errores += err_textos
        fotos = [a for a in request.files.getlist("fotos") if a and a.filename]
        if not fotos:
            errores.append("Sube al menos una foto de la vivienda.")
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("vendedor/form.html", v=valores, x=extra, p=None), 422
        p = Propiedad(vendedor_id=current_user.id, precio=datos["precio"], estado="pendiente", **textos,
                      **{c: datos[c] if c not in BOOLEANAS else bool(datos[c]) for c in Propiedad.CAMPOS_MODELO})
        errores_fotos = _guardar_fotos(p, fotos)
        if not p.fotos:
            for e in errores_fotos:
                flash(e, "error")
            return render_template("vendedor/form.html", v=valores, x=extra, p=None), 422
        db.session.add(p)
        db.session.commit()
        for e in errores_fotos:
            flash(e, "warning")
        flash("Publicación enviada. Será visible cuando el administrador la apruebe.", "ok")
        return redirect(url_for("vendedor.mis_publicaciones"))
    extra["precio"] = request.args.get("precio", "")
    return render_template("vendedor/form.html", v=precargado(request.args), x=extra, p=None)


@bp.route("/publicaciones/<int:propiedad_id>/editar", methods=["GET", "POST"])
@roles_required("vendedor")
def editar(propiedad_id):
    p = _propia(propiedad_id)
    if p.estado == "vendida":
        flash("Una vivienda vendida ya no puede editarse.", "warning")
        return redirect(url_for("vendedor.mis_publicaciones"))
    extra = {"titulo": p.titulo, "descripcion": p.descripcion, "direccion": p.direccion,
             "precio": f"{p.precio:g}"}
    if request.method == "POST":
        valores = desde_formulario(request.form)
        extra = {k: request.form.get(k, "").strip() for k in extra}
        datos, errores = limpiar_vivienda(request.form, exigir_precio=True)
        textos, err_textos = _validar_textos(request.form)
        errores += err_textos
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("vendedor/form.html", v=valores, x=extra, p=p), 422
        _aplicar(p, datos)
        p.precio = datos["precio"]
        p.titulo, p.descripcion, p.direccion = textos["titulo"], textos["descripcion"], textos["direccion"]
        for e in _guardar_fotos(p, request.files.getlist("fotos")):
            flash(e, "warning")
        if p.estado in ("aprobada", "rechazada"):
            p.estado, p.motivo_rechazo = "pendiente", None
            flash("Los cambios fueron guardados y la publicación volverá a revisión.", "ok")
        else:
            flash("Cambios guardados.", "ok")
        db.session.commit()
        return redirect(url_for("vendedor.mis_publicaciones"))
    return render_template("vendedor/form.html", v=desde_propiedad(p), x=extra, p=p)


@bp.route("/publicaciones/<int:propiedad_id>/eliminar", methods=["POST"])
@roles_required("vendedor")
def eliminar(propiedad_id):
    p = _propia(propiedad_id)
    services.eliminar_propiedad(p)
    flash("Publicación eliminada.", "ok")
    return redirect(url_for("vendedor.mis_publicaciones"))


@bp.route("/fotos/<int:foto_id>/eliminar", methods=["POST"])
@roles_required("vendedor")
def eliminar_foto(foto_id):
    f = db.get_or_404(Foto, foto_id)
    p = _propia(f.propiedad_id)
    if len(p.fotos) <= 1:
        flash("La publicación debe conservar al menos una foto.", "warning")
    else:
        nombre = f.archivo
        db.session.delete(f)
        db.session.commit()
        borrar_archivo_foto(nombre)
        flash("Foto eliminada.", "ok")
    return redirect(url_for("vendedor.editar", propiedad_id=p.id))


@bp.route("/publicaciones/<int:propiedad_id>/vendida", methods=["POST"])
@roles_required("vendedor")
def marcar_vendida(propiedad_id):
    p = _propia(propiedad_id)
    if p.estado != "aprobada":
        flash("Solo las publicaciones aprobadas pueden marcarse como vendidas.", "warning")
        return redirect(url_for("vendedor.mis_publicaciones"))
    datos, errores = limpiar_vivienda({**p.datos_modelo(), "precio": request.form.get("precio_final")}, exigir_precio=True)
    if errores:
        for e in errores:
            flash(e, "error")
        return redirect(url_for("vendedor.mis_publicaciones"))
    p.estado = "vendida"
    if request.form.get("aportar_dataset"):
        services.agregar_registro(datos, "venta")
        flash("¡Felicitaciones por la venta! Los datos se sumaron al histórico para mejorar el modelo.", "ok")
    else:
        flash("¡Felicitaciones por la venta!", "ok")
    db.session.commit()
    return redirect(url_for("vendedor.mis_publicaciones"))
