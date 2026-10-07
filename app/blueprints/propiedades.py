"""Catálogo público de viviendas: búsqueda, detalle, favoritos y comparador."""
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from .. import services
from ..extensions import db
from ..models import Favorito, Mensaje, Propiedad
from ..utils import ahora_lima, roles_required, url_segura

bp = Blueprint("propiedades", __name__)

MAX_COMPARAR = 4
ORDENES = {
    "recientes": ("Más recientes", lambda: Propiedad.creado_en.desc()),
    "precio_asc": ("Precio: menor a mayor", lambda: Propiedad.precio.asc()),
    "precio_desc": ("Precio: mayor a menor", lambda: Propiedad.precio.desc()),
    "m2_asc": ("Precio por m²: menor", lambda: (Propiedad.precio / Propiedad.area_construida).asc()),
    "area_desc": ("Mayor área construida", lambda: Propiedad.area_construida.desc()),
}


def _numero(nombre, tipo=float):
    valor = request.args.get(nombre, "").strip().replace(",", ".")
    if not valor:
        return None
    try:
        return tipo(valor)
    except ValueError:
        return None


def _volver(por_defecto):
    destino = request.form.get("next")
    return redirect(destino if url_segura(destino) else por_defecto)


@bp.route("/propiedades")
def catalogo():
    q = Propiedad.query.filter_by(estado="aprobada")
    texto = request.args.get("q", "").strip()
    if texto:
        patron = f"%{texto}%"
        q = q.filter(
            db.or_(Propiedad.titulo.ilike(patron), Propiedad.descripcion.ilike(patron), Propiedad.direccion.ilike(patron))
        )
    for campo in ("tipo", "distrito", "estado_conservacion", "acabados"):
        valor = request.args.get(campo, "").strip()
        if valor:
            q = q.filter(getattr(Propiedad, campo) == valor)
    if (v := _numero("precio_min")) is not None:
        q = q.filter(Propiedad.precio >= v)
    if (v := _numero("precio_max")) is not None:
        q = q.filter(Propiedad.precio <= v)
    if (v := _numero("area_min")) is not None:
        q = q.filter(Propiedad.area_construida >= v)
    if (v := _numero("area_max")) is not None:
        q = q.filter(Propiedad.area_construida <= v)
    if (v := _numero("habitaciones", int)) is not None:
        q = q.filter(Propiedad.habitaciones >= v)
    if (v := _numero("banos", int)) is not None:
        q = q.filter(Propiedad.banos >= v)
    if (v := _numero("antiguedad_max", int)) is not None:
        q = q.filter(Propiedad.antiguedad <= v)
    if (v := _numero("cochera", int)) is not None:
        q = q.filter(Propiedad.cochera >= v)
    for extra in ("jardin", "piscina", "ascensor", "seguridad"):
        if request.args.get(extra):
            q = q.filter(getattr(Propiedad, extra).is_(True))

    orden = request.args.get("orden", "recientes")
    if orden not in ORDENES:
        orden = "recientes"
    q = q.order_by(ORDENES[orden][1](), Propiedad.id.desc())
    pagina = request.args.get("pagina", 1, type=int)
    pag = q.paginate(page=pagina, per_page=9, error_out=False)

    favoritos = set()
    if current_user.is_authenticated:
        favoritos = {f.propiedad_id for f in Favorito.query.filter_by(usuario_id=current_user.id)}
    filtros = {k: v for k, v in request.args.items() if k != "pagina" and v}
    return render_template(
        "propiedades/catalogo.html", pag=pag, filtros=filtros, favoritos=favoritos,
        ordenes={k: v[0] for k, v in ORDENES.items()}, orden=orden,
    )


@bp.route("/propiedades/<int:propiedad_id>")
def detalle(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    es_dueno = current_user.is_authenticated and p.vendedor_id == current_user.id
    es_admin = current_user.is_authenticated and current_user.es_admin
    if p.estado != "aprobada" and not (es_dueno or es_admin):
        abort(404)

    est = services.estimar(p.datos_modelo(), con_factores=False)
    veredicto = services.veredicto_precio(p.precio, est["precio"])

    es_favorito = False
    hay_conversacion = False
    if current_user.is_authenticated:
        es_favorito = (
            Favorito.query.filter_by(usuario_id=current_user.id, propiedad_id=p.id).first() is not None
        )
        hay_conversacion = (
            Mensaje.query.filter_by(propiedad_id=p.id, comprador_id=current_user.id).first() is not None
        )
    en_comparador = p.id in session.get("comparar", [])
    # Primer horario válido para visitas: ≥ 2 h de anticipación, alineado a la media hora
    minimo_visita = (ahora_lima() + timedelta(hours=2)).replace(second=0, microsecond=0)
    minimo_visita += timedelta(minutes=(30 - minimo_visita.minute % 30) % 30)
    return render_template(
        "propiedades/detalle.html", p=p, est=est, veredicto=veredicto, es_favorito=es_favorito,
        es_dueno=es_dueno, en_comparador=en_comparador, hay_conversacion=hay_conversacion,
        minimo_visita=minimo_visita,
    )


# ------------------------------------------------------------------ favoritos
@bp.route("/favoritos")
@roles_required("comprador", "vendedor")
def favoritos():
    favs = (
        Favorito.query.filter_by(usuario_id=current_user.id)
        .join(Propiedad, Favorito.propiedad_id == Propiedad.id)
        .order_by(Favorito.creado_en.desc())
        .all()
    )
    return render_template("propiedades/favoritos.html", favs=favs)


@bp.route("/propiedades/<int:propiedad_id>/favorito", methods=["POST"])
@roles_required("comprador", "vendedor")
def favorito(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    existente = Favorito.query.filter_by(usuario_id=current_user.id, propiedad_id=p.id).first()
    if existente:
        db.session.delete(existente)
        flash("Quitada de tus favoritos.", "ok")
    elif p.estado != "aprobada":
        abort(404)
    else:
        db.session.add(Favorito(usuario_id=current_user.id, propiedad_id=p.id))
        flash("Guardada en tus favoritos.", "ok")
    db.session.commit()
    return _volver(url_for("propiedades.detalle", propiedad_id=p.id))


# ------------------------------------------------------------------ comparador
@bp.route("/comparar")
def comparar():
    ids = session.get("comparar", [])
    props = [p for p in (db.session.get(Propiedad, i) for i in ids) if p and p.estado == "aprobada"]
    session["comparar"] = [p.id for p in props]
    filas = []
    for p in props:
        est = services.estimar(p.datos_modelo(), con_factores=False)
        filas.append({"p": p, "est": est, "veredicto": services.veredicto_precio(p.precio, est["precio"])})
    mejor_m2 = min((f["p"].precio_m2 for f in filas), default=None)
    return render_template("propiedades/comparar.html", filas=filas, mejor_m2=mejor_m2, maximo=MAX_COMPARAR)


@bp.route("/comparar/agregar/<int:propiedad_id>", methods=["POST"])
def comparar_agregar(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    if p.estado != "aprobada":
        abort(404)
    ids = list(session.get("comparar", []))
    if p.id in ids:
        flash("Esa vivienda ya está en el comparador.", "warning")
    elif len(ids) >= MAX_COMPARAR:
        flash(f"Puedes comparar hasta {MAX_COMPARAR} viviendas. Quita una para agregar otra.", "warning")
    else:
        ids.append(p.id)
        session["comparar"] = ids
        flash("Agregada al comparador.", "ok")
    return _volver(url_for("propiedades.comparar"))


@bp.route("/comparar/quitar/<int:propiedad_id>", methods=["POST"])
def comparar_quitar(propiedad_id):
    session["comparar"] = [i for i in session.get("comparar", []) if i != propiedad_id]
    return _volver(url_for("propiedades.comparar"))


@bp.route("/comparar/vaciar", methods=["POST"])
def comparar_vaciar():
    session["comparar"] = []
    return redirect(url_for("propiedades.catalogo"))
