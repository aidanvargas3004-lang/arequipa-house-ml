"""Registro, inicio de sesión, cierre de sesión y perfil."""
import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import Usuario
from ..utils import url_segura

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_clave(clave: str) -> str | None:
    if len(clave) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        return "La contraseña debe combinar letras y números."
    if len(clave) > 128:
        return "La contraseña es demasiado larga."
    return None


def _destino_post_login(usuario: Usuario):
    siguiente = request.args.get("next") or request.form.get("next")
    if url_segura(siguiente):
        return redirect(siguiente)
    if usuario.es_admin:
        return redirect(url_for("admin.panel"))
    if usuario.rol == "vendedor":
        return redirect(url_for("vendedor.mis_publicaciones"))
    return redirect(url_for("main.inicio"))


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    valores = {"nombre": "", "email": "", "telefono": "", "rol": "comprador"}
    if request.method == "POST":
        valores = {
            "nombre": request.form.get("nombre", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "telefono": request.form.get("telefono", "").strip(),
            "rol": request.form.get("rol", "comprador"),
        }
        clave = request.form.get("password", "")
        errores = []
        if len(valores["nombre"]) < 3 or len(valores["nombre"]) > 120:
            errores.append("Ingresa tu nombre completo (3 a 120 caracteres).")
        if not EMAIL_RE.match(valores["email"]) or len(valores["email"]) > 160:
            errores.append("Ingresa un correo electrónico válido.")
        elif Usuario.query.filter_by(email=valores["email"]).first():
            errores.append("Ese correo ya está registrado.")
        if valores["rol"] not in ("comprador", "vendedor"):
            errores.append("Elige si eres comprador o vendedor.")
        if valores["telefono"] and not re.fullmatch(r"[0-9+\s()-]{6,30}", valores["telefono"]):
            errores.append("El teléfono solo puede contener números, espacios, + ( ) y guiones.")
        if (e := validar_clave(clave)):
            errores.append(e)
        if clave != request.form.get("password2", ""):
            errores.append("Las contraseñas no coinciden.")
        if not request.form.get("acepta"):
            errores.append("Debes aceptar los términos y la política de privacidad.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            u = Usuario(
                nombre=valores["nombre"], email=valores["email"], rol=valores["rol"],
                telefono=valores["telefono"] or None,
            )
            u.set_password(clave)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            u.registrar_acceso()
            db.session.commit()
            flash(f"¡Bienvenido/a, {u.nombre.split()[0]}! Tu cuenta fue creada.", "ok")
            return _destino_post_login(u)
    return render_template("auth/registro.html", v=valores)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("password", "")
        u = Usuario.query.filter_by(email=email).first()
        cfg = current_app.config
        if u and u.esta_bloqueado:
            flash("Demasiados intentos fallidos. Intenta de nuevo en unos minutos.", "error")
        elif u and u.check_password(clave):
            if not u.activo:
                flash("Tu cuenta está suspendida. Contacta al administrador.", "error")
            else:
                login_user(u, remember=bool(request.form.get("recordar")))
                u.registrar_acceso()
                db.session.commit()
                return _destino_post_login(u)
        else:
            if u:
                u.registrar_fallo(cfg["MAX_FAILED_LOGINS"], cfg["LOCK_MINUTES"])
                db.session.commit()
            flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth/login.html", email=email)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("main.inicio"))


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "datos":
            nombre = request.form.get("nombre", "").strip()
            telefono = request.form.get("telefono", "").strip()
            if len(nombre) < 3 or len(nombre) > 120:
                flash("Ingresa un nombre válido (3 a 120 caracteres).", "error")
            elif telefono and not re.fullmatch(r"[0-9+\s()-]{6,30}", telefono):
                flash("Teléfono no válido.", "error")
            else:
                current_user.nombre = nombre
                current_user.telefono = telefono or None
                db.session.commit()
                flash("Datos actualizados.", "ok")
        elif accion == "clave":
            actual = request.form.get("actual", "")
            nueva = request.form.get("nueva", "")
            if not current_user.check_password(actual):
                flash("La contraseña actual no es correcta.", "error")
            elif (e := validar_clave(nueva)):
                flash(e, "error")
            elif nueva != request.form.get("nueva2", ""):
                flash("Las contraseñas nuevas no coinciden.", "error")
            else:
                current_user.set_password(nueva)
                db.session.commit()
                flash("Contraseña actualizada.", "ok")
        return redirect(url_for("auth.perfil"))
    return render_template("auth/perfil.html")
