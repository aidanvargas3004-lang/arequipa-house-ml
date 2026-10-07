"""Utilidades compartidas: control de acceso, redirecciones seguras y fotos."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import abort, current_app
from flask_login import current_user
from PIL import Image, ImageOps

from .extensions import login_manager
from .models import ahora

Image.MAX_IMAGE_PIXELS = 40_000_000  # evita "bombas de descompresión"
FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP"}
UTC_LIMA = timedelta(hours=-5)  # Perú no usa horario de verano


def a_lima(dt: datetime | None) -> datetime | None:
    return dt + UTC_LIMA if dt else None


def ahora_lima() -> datetime:
    return ahora() + UTC_LIMA


def roles_required(*roles: str):
    """Exige sesión iniciada y uno de los roles indicados (403 si no corresponde)."""

    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.rol not in roles:
                abort(403)
            return f(*args, **kwargs)

        return envoltura

    return decorador


def url_segura(destino: str | None) -> bool:
    """Solo se aceptan rutas relativas internas en el parámetro ``next``."""
    if not destino or not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        return False
    partes = urlparse(destino)
    return not partes.scheme and not partes.netloc


def carpeta_subidas() -> Path:
    p = Path(current_app.config["UPLOAD_FOLDER"])
    p.mkdir(parents=True, exist_ok=True)
    return p


def guardar_imagen_bytes(data: bytes) -> str:
    """Valida, normaliza (JPEG ≤ 1600 px) y guarda una imagen. Devuelve el nombre de archivo."""
    try:
        img = Image.open(io.BytesIO(data))
        formato = img.format
        img.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("El archivo no es una imagen válida.") from exc
    if formato not in FORMATOS_PERMITIDOS:
        raise ValueError("Formato no permitido: use JPG, PNG o WEBP.")
    img.thumbnail((1600, 1600))
    nombre = f"{uuid.uuid4().hex}.jpg"
    img.save(carpeta_subidas() / nombre, "JPEG", quality=85, optimize=True)
    return nombre


def guardar_foto(archivo) -> str:
    limite = current_app.config["MAX_PHOTO_BYTES"]
    data = archivo.read(limite + 1)
    if len(data) > limite:
        raise ValueError(f"Cada foto debe pesar menos de {limite // (1024 * 1024)} MB.")
    if not data:
        raise ValueError("El archivo está vacío.")
    return guardar_imagen_bytes(data)


def borrar_archivo_foto(nombre: str) -> None:
    ruta = carpeta_subidas() / Path(nombre).name  # Path.name evita salirse de la carpeta
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
