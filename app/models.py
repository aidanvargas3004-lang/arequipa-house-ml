"""Modelos de base de datos (SQLAlchemy). Compatibles con SQLite y PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

ROLES = ("comprador", "vendedor", "administrador")


def ahora() -> datetime:
    """Fecha/hora UTC sin zona (consistente entre SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), nullable=False, unique=True, index=True)
    telefono = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="comprador")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    intentos_fallidos = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_hasta = db.Column(db.DateTime)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)
    ultimo_acceso = db.Column(db.DateTime)

    propiedades = db.relationship("Propiedad", back_populates="vendedor", lazy="dynamic")
    tasaciones = db.relationship("Tasacion", back_populates="usuario", lazy="dynamic")

    def set_password(self, clave: str) -> None:
        self.password_hash = generate_password_hash(clave)

    def check_password(self, clave: str) -> bool:
        return check_password_hash(self.password_hash, clave)

    @property
    def is_active(self) -> bool:  # Flask-Login
        return bool(self.activo)

    @property
    def es_admin(self) -> bool:
        return self.rol == "administrador"

    @property
    def esta_bloqueado(self) -> bool:
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > ahora())

    def registrar_fallo(self, maximo: int, minutos: int) -> None:
        self.intentos_fallidos = (self.intentos_fallidos or 0) + 1
        if self.intentos_fallidos >= maximo:
            self.bloqueado_hasta = ahora() + timedelta(minutes=minutos)
            self.intentos_fallidos = 0

    def registrar_acceso(self) -> None:
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.ultimo_acceso = ahora()


@login_manager.user_loader
def cargar_usuario(user_id: str):
    return db.session.get(Usuario, int(user_id))


class Propiedad(db.Model):
    __tablename__ = "propiedades"

    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    titulo = db.Column(db.String(160), nullable=False)
    descripcion = db.Column(db.Text, nullable=False, default="")
    direccion = db.Column(db.String(200), nullable=False, default="")

    tipo = db.Column(db.String(20), nullable=False, index=True)
    distrito = db.Column(db.String(60), nullable=False, index=True)
    area_terreno = db.Column(db.Float, nullable=False)
    area_construida = db.Column(db.Float, nullable=False)
    habitaciones = db.Column(db.Integer, nullable=False)
    banos = db.Column(db.Integer, nullable=False)
    pisos = db.Column(db.Integer, nullable=False, default=1)
    antiguedad = db.Column(db.Integer, nullable=False, default=0)
    estado_conservacion = db.Column(db.String(20), nullable=False, default="Bueno")
    acabados = db.Column(db.String(20), nullable=False, default="Estándar")
    cochera = db.Column(db.Integer, nullable=False, default=0)
    jardin = db.Column(db.Boolean, nullable=False, default=False)
    piscina = db.Column(db.Boolean, nullable=False, default=False)
    ascensor = db.Column(db.Boolean, nullable=False, default=False)
    seguridad = db.Column(db.Boolean, nullable=False, default=False)
    cerca_colegios = db.Column(db.Boolean, nullable=False, default=False)
    cerca_hospitales = db.Column(db.Boolean, nullable=False, default=False)
    cerca_comercial = db.Column(db.Boolean, nullable=False, default=False)
    transporte_publico = db.Column(db.Boolean, nullable=False, default=False)

    precio = db.Column(db.Float, nullable=False, index=True)
    # pendiente → aprobada | rechazada ; aprobada → vendida
    estado = db.Column(db.String(15), nullable=False, default="pendiente", index=True)
    motivo_rechazo = db.Column(db.String(300))
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)

    vendedor = db.relationship("Usuario", back_populates="propiedades")
    fotos = db.relationship(
        "Foto", back_populates="propiedad", cascade="all, delete-orphan", order_by="Foto.orden, Foto.id"
    )

    CAMPOS_MODELO = (
        "tipo", "distrito", "area_terreno", "area_construida", "habitaciones", "banos", "pisos",
        "antiguedad", "estado_conservacion", "acabados", "cochera", "jardin", "piscina", "ascensor",
        "seguridad", "cerca_colegios", "cerca_hospitales", "cerca_comercial", "transporte_publico",
    )

    def datos_modelo(self) -> dict:
        """Características de la vivienda en el formato que espera el modelo."""
        d = {c: getattr(self, c) for c in self.CAMPOS_MODELO}
        for c in ("jardin", "piscina", "ascensor", "seguridad", "cerca_colegios",
                  "cerca_hospitales", "cerca_comercial", "transporte_publico"):
            d[c] = int(bool(d[c]))
        return d

    @property
    def precio_m2(self) -> float:
        return self.precio / self.area_construida if self.area_construida else 0.0

    @property
    def foto_principal(self):
        return self.fotos[0] if self.fotos else None

    @property
    def visible(self) -> bool:
        return self.estado == "aprobada"


class Foto(db.Model):
    __tablename__ = "fotos"

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey("propiedades.id"), nullable=False, index=True)
    archivo = db.Column(db.String(120), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    propiedad = db.relationship("Propiedad", back_populates="fotos")


class Favorito(db.Model):
    __tablename__ = "favoritos"
    __table_args__ = (db.UniqueConstraint("usuario_id", "propiedad_id", name="uq_favorito"),)

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey("propiedades.id"), nullable=False, index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    propiedad = db.relationship("Propiedad")


class Mensaje(db.Model):
    """Mensaje dentro de una conversación (propiedad + comprador interesado)."""

    __tablename__ = "mensajes"

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey("propiedades.id"), nullable=False, index=True)
    comprador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    leido = db.Column(db.Boolean, nullable=False, default=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora, index=True)

    propiedad = db.relationship("Propiedad")
    comprador = db.relationship("Usuario", foreign_keys=[comprador_id])
    autor = db.relationship("Usuario", foreign_keys=[autor_id])


class Visita(db.Model):
    __tablename__ = "visitas"

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey("propiedades.id"), nullable=False, index=True)
    comprador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha_hora = db.Column(db.DateTime, nullable=False)
    modalidad = db.Column(db.String(15), nullable=False, default="presencial")
    comentario = db.Column(db.String(400))
    # pendiente | confirmada | rechazada | cancelada
    estado = db.Column(db.String(15), nullable=False, default="pendiente", index=True)
    respuesta = db.Column(db.String(300))
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    propiedad = db.relationship("Propiedad")
    comprador = db.relationship("Usuario")


class Tasacion(db.Model):
    """Historial de estimaciones realizadas por los usuarios."""

    __tablename__ = "tasaciones"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey("modelos_ml.id"))
    propiedad_id = db.Column(db.Integer, db.ForeignKey("propiedades.id"))
    datos = db.Column(db.JSON, nullable=False)
    precio_estimado = db.Column(db.Float, nullable=False)
    precio_min = db.Column(db.Float, nullable=False)
    precio_max = db.Column(db.Float, nullable=False)
    precio_m2 = db.Column(db.Float, nullable=False)
    factores = db.Column(db.JSON, nullable=False, default=list)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora, index=True)

    usuario = db.relationship("Usuario", back_populates="tasaciones")
    modelo = db.relationship("ModeloML")


class ModeloML(db.Model):
    """Versión de modelo entrenado (el archivo vive en MODELS_FOLDER)."""

    __tablename__ = "modelos_ml"

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, unique=True)
    algoritmo = db.Column(db.String(30))
    archivo = db.Column(db.String(120))
    # entrenando | listo | error
    estado = db.Column(db.String(12), nullable=False, default="entrenando")
    activo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    metricas = db.Column(db.JSON)
    composicion = db.Column(db.JSON)  # registros por origen del dataset
    error = db.Column(db.String(400))
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)
    terminado_en = db.Column(db.DateTime)

    creado_por = db.relationship("Usuario")

    @property
    def algoritmo_nombre(self) -> str:
        from .ml.pipeline import ALGORITMOS

        return ALGORITMOS.get(self.algoritmo or "", "—")

    @property
    def metricas_ganador(self) -> dict:
        if not self.metricas:
            return {}
        return self.metricas["algoritmos"][self.metricas["ganador"]]["prueba"]

    @property
    def origen_datos(self) -> str:
        """sintetico | mixto | real (según la composición del dataset de entrenamiento)."""
        comp = self.composicion or {}
        total = sum(comp.values()) or 1
        sint = comp.get("sintetico", 0)
        if sint / total >= 0.99:
            return "sintetico"
        if sint == 0:
            return "real"
        return "mixto"


class DatasetRegistro(db.Model):
    """Registro histórico de vivienda con su precio (insumo de entrenamiento)."""

    __tablename__ = "dataset_registros"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    distrito = db.Column(db.String(60), nullable=False, index=True)
    area_terreno = db.Column(db.Float, nullable=False)
    area_construida = db.Column(db.Float, nullable=False)
    habitaciones = db.Column(db.Integer, nullable=False)
    banos = db.Column(db.Integer, nullable=False)
    pisos = db.Column(db.Integer, nullable=False)
    antiguedad = db.Column(db.Integer, nullable=False)
    estado_conservacion = db.Column(db.String(20), nullable=False)
    acabados = db.Column(db.String(20), nullable=False)
    cochera = db.Column(db.Integer, nullable=False, default=0)
    jardin = db.Column(db.Integer, nullable=False, default=0)
    piscina = db.Column(db.Integer, nullable=False, default=0)
    ascensor = db.Column(db.Integer, nullable=False, default=0)
    seguridad = db.Column(db.Integer, nullable=False, default=0)
    cerca_colegios = db.Column(db.Integer, nullable=False, default=0)
    cerca_hospitales = db.Column(db.Integer, nullable=False, default=0)
    cerca_comercial = db.Column(db.Integer, nullable=False, default=0)
    transporte_publico = db.Column(db.Integer, nullable=False, default=0)
    precio = db.Column(db.Float, nullable=False)
    origen = db.Column(db.String(15), nullable=False, default="manual", index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    @property
    def precio_m2(self) -> float:
        return self.precio / self.area_construida if self.area_construida else 0.0


class Parametro(db.Model):
    """Parámetros globales de tasación editables por el administrador."""

    __tablename__ = "parametros"

    clave = db.Column(db.String(60), primary_key=True)
    valor = db.Column(db.String(60), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False, default="")


class AjusteDistrito(db.Model):
    """Factor multiplicativo por distrito (p. ej. si sube el valor del suelo)."""

    __tablename__ = "ajustes_distrito"

    distrito = db.Column(db.String(60), primary_key=True)
    factor = db.Column(db.Float, nullable=False, default=1.0)
