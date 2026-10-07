"""Panel de administración: estadísticas, usuarios, moderación, dataset, modelos y parámetros."""
import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from .. import services
from ..extensions import db
from ..forms import desde_formulario, desde_propiedad
from ..ml.constants import (
    DISTRITO_NOMBRES, FEATURE_COLUMNS, ORIGEN_ETIQUETA, TARGET,
)
from ..ml.schema import limpiar_vivienda
from ..models import (
    AjusteDistrito, DatasetRegistro, ModeloML, Mensaje, Propiedad, Tasacion, Usuario, Visita, ROLES, ahora,
)
from ..utils import roles_required
from .auth import EMAIL_RE, validar_clave
from .vendedor import _aplicar, _guardar_fotos, _validar_textos

bp = Blueprint("admin", __name__, url_prefix="/admin")
solo_admin = roles_required("administrador")


def _csv_respuesta(nombre: str, cabecera: list, filas) -> Response:
    buf = io.StringIO()
    escritor = csv.writer(buf)
    escritor.writerow(cabecera)
    escritor.writerows(filas)
    return Response(
        "﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


# ------------------------------------------------------------------ panel
@bp.route("/")
@solo_admin
def panel():
    por_rol = dict(db.session.query(Usuario.rol, func.count()).group_by(Usuario.rol).all())
    por_estado = dict(db.session.query(Propiedad.estado, func.count()).group_by(Propiedad.estado).all())
    desde = ahora() - timedelta(days=29)
    por_dia = {
        str(d): n
        for d, n in db.session.query(func.date(Tasacion.creado_en), func.count())
        .filter(Tasacion.creado_en >= desde)
        .group_by(func.date(Tasacion.creado_en))
        .all()
    }
    serie = []
    for i in range(30):
        dia = (desde + timedelta(days=i)).date()
        serie.append({"dia": dia.strftime("%d/%m"), "n": por_dia.get(str(dia), 0)})
    m2 = (
        db.session.query(DatasetRegistro.distrito, func.avg(DatasetRegistro.precio / DatasetRegistro.area_construida))
        .group_by(DatasetRegistro.distrito)
        .all()
    )
    m2 = sorted(((d, round(float(v))) for d, v in m2), key=lambda x: x[1], reverse=True)
    stats = {
        "usuarios": sum(por_rol.values()), "por_rol": por_rol,
        "propiedades": sum(por_estado.values()), "por_estado": por_estado,
        "tasaciones": Tasacion.query.count(),
        "visitas_pendientes": Visita.query.filter_by(estado="pendiente").count(),
        "mensajes": Mensaje.query.count(),
        "dataset": services.composicion_dataset(),
    }
    return render_template(
        "admin/panel.html", stats=stats, serie=serie, m2=m2, modelo=services.modelo_activo(),
        origen_etiqueta=ORIGEN_ETIQUETA,
    )


# ---------------------------------------------------------------- usuarios
@bp.route("/usuarios")
@solo_admin
def usuarios():
    q = Usuario.query
    texto = request.args.get("q", "").strip()
    rol = request.args.get("rol", "")
    if texto:
        q = q.filter(db.or_(Usuario.nombre.ilike(f"%{texto}%"), Usuario.email.ilike(f"%{texto}%")))
    if rol in ROLES:
        q = q.filter_by(rol=rol)
    pag = q.order_by(Usuario.creado_en.desc()).paginate(
        page=request.args.get("pagina", 1, type=int), per_page=15, error_out=False
    )
    return render_template("admin/usuarios.html", pag=pag, roles=ROLES, q=texto, rol=rol)


def _otros_admins_activos(excluir_id: int) -> int:
    return Usuario.query.filter(
        Usuario.rol == "administrador", Usuario.activo.is_(True), Usuario.id != excluir_id
    ).count()


@bp.route("/usuarios/<int:usuario_id>/actualizar", methods=["POST"])
@solo_admin
def usuario_actualizar(usuario_id):
    u = db.get_or_404(Usuario, usuario_id)
    rol = request.form.get("rol", u.rol)
    activo = bool(request.form.get("activo"))
    if rol not in ROLES:
        abort(400)
    if u.id == current_user.id and (rol != u.rol or not activo):
        flash("No puedes cambiar tu propio rol ni suspender tu propia cuenta.", "warning")
    elif u.rol == "administrador" and (rol != "administrador" or not activo) and _otros_admins_activos(u.id) == 0:
        flash("Debe existir al menos un administrador activo.", "warning")
    else:
        u.rol, u.activo = rol, activo
        if activo:
            u.bloqueado_hasta, u.intentos_fallidos = None, 0
        db.session.commit()
        flash(f"Usuario {u.email} actualizado.", "ok")
    return redirect(request.referrer or url_for("admin.usuarios"))


@bp.route("/usuarios/nuevo", methods=["POST"])
@solo_admin
def usuario_nuevo():
    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    rol = request.form.get("rol", "comprador")
    clave = request.form.get("password", "")
    errores = []
    if len(nombre) < 3:
        errores.append("Ingresa el nombre completo.")
    if not EMAIL_RE.match(email):
        errores.append("Correo no válido.")
    elif Usuario.query.filter_by(email=email).first():
        errores.append("Ese correo ya está registrado.")
    if rol not in ROLES:
        errores.append("Rol no válido.")
    if (e := validar_clave(clave)):
        errores.append(e)
    if errores:
        for e in errores:
            flash(e, "error")
    else:
        u = Usuario(nombre=nombre, email=email, rol=rol)
        u.set_password(clave)
        db.session.add(u)
        db.session.commit()
        flash(f"Usuario {email} creado.", "ok")
    return redirect(url_for("admin.usuarios"))


# ----------------------------------------------------------- publicaciones
@bp.route("/publicaciones")
@solo_admin
def publicaciones():
    estado = request.args.get("estado", "pendiente")
    q = Propiedad.query
    if estado in ("pendiente", "aprobada", "rechazada", "vendida"):
        q = q.filter_by(estado=estado)
    else:
        estado = "todas"
    pag = q.order_by(Propiedad.creado_en.desc()).paginate(
        page=request.args.get("pagina", 1, type=int), per_page=12, error_out=False
    )
    cuenta = dict(db.session.query(Propiedad.estado, func.count()).group_by(Propiedad.estado).all())
    return render_template("admin/publicaciones.html", pag=pag, estado=estado, cuenta=cuenta)


@bp.route("/publicaciones/<int:propiedad_id>/moderar", methods=["POST"])
@solo_admin
def moderar(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    accion = request.form.get("accion")
    if accion == "aprobar":
        p.estado, p.motivo_rechazo = "aprobada", None
        flash("Publicación aprobada y visible en el catálogo.", "ok")
    elif accion == "rechazar":
        motivo = request.form.get("motivo", "").strip()
        if len(motivo) < 5:
            flash("Indica el motivo del rechazo (mínimo 5 caracteres).", "error")
            return redirect(request.referrer or url_for("admin.publicaciones"))
        p.estado, p.motivo_rechazo = "rechazada", motivo[:300]
        flash("Publicación rechazada. El vendedor verá el motivo.", "ok")
    elif accion == "eliminar":
        services.eliminar_propiedad(p)
        flash("Publicación eliminada.", "ok")
        return redirect(request.referrer or url_for("admin.publicaciones"))
    else:
        abort(400)
    db.session.commit()
    return redirect(url_for("admin.publicaciones", estado="pendiente"))


@bp.route("/publicaciones/<int:propiedad_id>/editar", methods=["GET", "POST"])
@solo_admin
def publicacion_editar(propiedad_id):
    p = db.get_or_404(Propiedad, propiedad_id)
    extra = {"titulo": p.titulo, "descripcion": p.descripcion, "direccion": p.direccion, "precio": f"{p.precio:g}"}
    if request.method == "POST":
        valores = desde_formulario(request.form)
        extra = {k: request.form.get(k, "").strip() for k in extra}
        datos, errores = limpiar_vivienda(request.form, exigir_precio=True)
        textos, err_textos = _validar_textos(request.form)
        errores += err_textos
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("vendedor/form.html", v=valores, x=extra, p=p, admin=True), 422
        _aplicar(p, datos)
        p.precio = datos["precio"]
        p.titulo, p.descripcion, p.direccion = textos["titulo"], textos["descripcion"], textos["direccion"]
        for e in _guardar_fotos(p, request.files.getlist("fotos")):
            flash(e, "warning")
        db.session.commit()
        flash("Publicación actualizada.", "ok")
        return redirect(url_for("admin.publicaciones", estado="todas"))
    return render_template("vendedor/form.html", v=desde_propiedad(p), x=extra, p=p, admin=True)


# ----------------------------------------------------------------- dataset
def _filtrar_dataset():
    q = DatasetRegistro.query
    origen = request.args.get("origen", "")
    distrito = request.args.get("distrito", "")
    tipo = request.args.get("tipo", "")
    if origen:
        q = q.filter_by(origen=origen)
    if distrito:
        q = q.filter_by(distrito=distrito)
    if tipo:
        q = q.filter_by(tipo=tipo)
    return q


@bp.route("/dataset")
@solo_admin
def dataset():
    pag = _filtrar_dataset().order_by(DatasetRegistro.id.desc()).paginate(
        page=request.args.get("pagina", 1, type=int), per_page=20, error_out=False
    )
    filtros = {k: v for k, v in request.args.items() if k != "pagina" and v}
    return render_template(
        "admin/dataset.html", pag=pag, filtros=filtros, comp=services.composicion_dataset(),
        origen_etiqueta=ORIGEN_ETIQUETA,
    )


@bp.route("/dataset/nuevo", methods=["GET", "POST"])
@bp.route("/dataset/<int:registro_id>/editar", methods=["GET", "POST"])
@solo_admin
def dataset_form(registro_id=None):
    reg = db.get_or_404(DatasetRegistro, registro_id) if registro_id else None
    if request.method == "POST":
        valores = desde_formulario(request.form)
        precio = request.form.get("precio", "").strip()
        datos, errores = limpiar_vivienda(request.form, exigir_precio=True)
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("admin/dataset_form.html", v=valores, precio=precio, reg=reg), 422
        if reg is None:
            services.agregar_registro(datos, "manual")
            flash("Registro agregado al histórico.", "ok")
        else:
            for c in FEATURE_COLUMNS + [TARGET]:
                setattr(reg, c, datos[c])
            flash("Registro actualizado.", "ok")
        db.session.commit()
        return redirect(url_for("admin.dataset"))
    if reg:
        return render_template("admin/dataset_form.html", v=desde_propiedad(reg), precio=f"{reg.precio:g}", reg=reg)
    from ..forms import valores_por_defecto

    return render_template("admin/dataset_form.html", v=valores_por_defecto(), precio="", reg=None)


@bp.route("/dataset/<int:registro_id>/eliminar", methods=["POST"])
@solo_admin
def dataset_eliminar(registro_id):
    db.session.delete(db.get_or_404(DatasetRegistro, registro_id))
    db.session.commit()
    flash("Registro eliminado.", "ok")
    return redirect(request.referrer or url_for("admin.dataset"))


@bp.route("/dataset/eliminar-origen", methods=["POST"])
@solo_admin
def dataset_eliminar_origen():
    origen = request.form.get("origen", "")
    if origen not in ORIGEN_ETIQUETA or request.form.get("confirmar") != "si":
        flash("Confirma la eliminación para continuar.", "warning")
    else:
        n = DatasetRegistro.query.filter_by(origen=origen).delete()
        db.session.commit()
        flash(f"Se eliminaron {n:,} registros de origen «{ORIGEN_ETIQUETA[origen]}».", "ok")
    return redirect(url_for("admin.dataset"))


@bp.route("/dataset/importar", methods=["POST"])
@solo_admin
def dataset_importar():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Selecciona un archivo CSV.", "error")
        return redirect(url_for("admin.dataset"))
    contenido = archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        flash("El archivo supera los 5 MB.", "error")
        return redirect(url_for("admin.dataset"))
    try:
        r = services.importar_csv(contenido, reemplazar_sinteticos=bool(request.form.get("reemplazar")))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.dataset"))
    flash(f"Importación completada: {r['importados']:,} registros nuevos, {r['omitidos']:,} omitidos.", "ok")
    if r["eliminados_sinteticos"]:
        flash(f"Se eliminaron {r['eliminados_sinteticos']:,} registros sintéticos.", "ok")
    for a in r["advertencias"]:
        flash(a, "warning")
    for e in r["errores"][:8]:
        flash(e, "warning")
    if r["omitidos"] > 8:
        flash(f"… y {r['omitidos'] - 8} filas omitidas más.", "warning")
    flash("Reentrena el modelo desde «Modelos» para que use los nuevos datos.", "info")
    return redirect(url_for("admin.dataset"))


@bp.route("/dataset/exportar")
@solo_admin
def dataset_exportar():
    filas = _filtrar_dataset().order_by(DatasetRegistro.id).all()
    return _csv_respuesta(
        "dataset_viviendas.csv", FEATURE_COLUMNS + [TARGET, "origen"],
        ([getattr(r, c) for c in FEATURE_COLUMNS + [TARGET, "origen"]] for r in filas),
    )


@bp.route("/dataset/plantilla")
@solo_admin
def dataset_plantilla():
    cab = FEATURE_COLUMNS + [TARGET]
    ejemplos = [
        ["Departamento", "Cayma", 95, 95, 3, 2, 1, 6, "Bueno", "Alta calidad", 1, 0, 0, 1, 1, 1, 0, 1, 1, 520000],
        ["Casa", "Paucarpata", 180, 140, 4, 3, 2, 12, "Regular", "Estándar", 1, 1, 0, 0, 0, 1, 0, 1, 1, 430000],
    ]
    return _csv_respuesta("plantilla_dataset.csv", cab, ejemplos)


# ------------------------------------------------------------------ modelos
@bp.route("/modelos")
@solo_admin
def modelos():
    lista = ModeloML.query.order_by(ModeloML.version.desc()).all()
    en_curso = any(m.estado == "entrenando" for m in lista)
    return render_template(
        "admin/modelos.html", modelos=lista, en_curso=en_curso, n_registros=DatasetRegistro.query.count(),
        comp=services.composicion_dataset(),
    )


@bp.route("/modelos/estado")
@solo_admin
def modelos_estado():
    return jsonify(
        [{"id": m.id, "estado": m.estado, "activo": m.activo} for m in ModeloML.query.all()]
    )


@bp.route("/modelos/entrenar", methods=["POST"])
@solo_admin
def modelo_entrenar():
    try:
        services.lanzar_entrenamiento(current_user.id, activar=bool(request.form.get("activar")))
        flash("Entrenamiento iniciado en segundo plano. El modelo actual sigue atendiendo estimaciones.", "ok")
    except services.EntrenamientoEnCurso as e:
        flash(str(e), "warning")
    return redirect(url_for("admin.modelos"))


@bp.route("/modelos/<int:modelo_id>")
@solo_admin
def modelo_detalle(modelo_id):
    m = db.get_or_404(ModeloML, modelo_id)
    if m.estado != "listo" or not m.metricas:
        flash(
            "Ese modelo aún se está entrenando." if m.estado == "entrenando" else f"Ese modelo no tiene métricas ({m.error or m.estado}).",
            "warning",
        )
        return redirect(url_for("admin.modelos"))
    return render_template("admin/modelo_detalle.html", mod=m, origen_etiqueta=ORIGEN_ETIQUETA)


@bp.route("/modelos/<int:modelo_id>/activar", methods=["POST"])
@solo_admin
def modelo_activar(modelo_id):
    m = db.get_or_404(ModeloML, modelo_id)
    try:
        services.activar_modelo(m)
        flash(f"Modelo v{m.version} activado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.modelos"))


@bp.route("/modelos/<int:modelo_id>/eliminar", methods=["POST"])
@solo_admin
def modelo_eliminar(modelo_id):
    m = db.get_or_404(ModeloML, modelo_id)
    if m.activo:
        flash("No puedes eliminar el modelo activo.", "warning")
    elif m.estado == "entrenando":
        flash("Espera a que termine el entrenamiento.", "warning")
    else:
        if m.archivo:
            (services.carpeta_modelos() / m.archivo).unlink(missing_ok=True)
        Tasacion.query.filter_by(modelo_id=m.id).update({Tasacion.modelo_id: None})
        db.session.delete(m)
        db.session.commit()
        flash("Versión eliminada.", "ok")
    return redirect(url_for("admin.modelos"))


# --------------------------------------------------------------- parámetros
@bp.route("/parametros", methods=["GET", "POST"])
@solo_admin
def parametros():
    if request.method == "POST":
        try:
            for clave in services.PARAMETROS_BASE:
                valor = float(request.form.get(clave, "").replace(",", "."))
                services.guardar_parametro(clave, valor)
            minimo, maximo = services.LIMITES_AJUSTE
            for d in DISTRITO_NOMBRES:
                bruto = request.form.get(f"ajuste_{d}", "1").replace(",", ".")
                factor = float(bruto)
                if not minimo <= factor <= maximo:
                    raise ValueError(f"El ajuste de {d} debe estar entre {minimo:g} y {maximo:g}.")
                a = db.session.get(AjusteDistrito, d) or AjusteDistrito(distrito=d)
                a.factor = factor
                db.session.add(a)
            db.session.commit()
            flash("Parámetros de tasación actualizados. Se aplican desde la próxima estimación.", "ok")
        except ValueError as e:
            db.session.rollback()
            flash(f"Valor no válido: {e}", "error")
        return redirect(url_for("admin.parametros"))
    ajustes = {a.distrito: a.factor for a in AjusteDistrito.query.all()}
    return render_template(
        "admin/parametros.html",
        params={c: services.obtener_parametro(c) for c in services.PARAMETROS_BASE},
        descripciones={c: d for c, (_, d) in services.PARAMETROS_BASE.items()},
        limites=services.LIMITES_PARAM,
        ajustes=[(d, ajustes.get(d, 1.0)) for d in DISTRITO_NOMBRES],
    )


# --------------------------------------------------------------- tasaciones
@bp.route("/tasaciones")
@solo_admin
def tasaciones():
    pag = Tasacion.query.order_by(Tasacion.creado_en.desc()).paginate(
        page=request.args.get("pagina", 1, type=int), per_page=20, error_out=False
    )
    return render_template("admin/tasaciones.html", pag=pag)


@bp.route("/tasaciones/exportar")
@solo_admin
def tasaciones_exportar():
    filas = Tasacion.query.order_by(Tasacion.id).all()
    return _csv_respuesta(
        "tasaciones.csv",
        ["id", "fecha_utc", "usuario", "tipo", "distrito", "area_construida", "precio_estimado", "precio_min", "precio_max", "precio_m2", "modelo"],
        (
            [t.id, t.creado_en.isoformat(sep=" ", timespec="seconds"), t.usuario.email, t.datos.get("tipo"),
             t.datos.get("distrito"), t.datos.get("area_construida"), t.precio_estimado, t.precio_min,
             t.precio_max, t.precio_m2, f"v{t.modelo.version}" if t.modelo else ""]
            for t in filas
        ),
    )
