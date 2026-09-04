from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    imagen_url = Column(String, nullable=True)
    tienda = Column(String)
    categoria = Column(String, nullable=True)
    precio_actual = Column(Float)
    precio_original = Column(Float, nullable=True)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow)
    # NUEVO: evolución hacia deduplicación por tienda+external_id. Todos
    # nullable=True durante la transición: ningún scraper los provee de
    # forma consistente todavía. disponible=NULL representa "desconocido",
    # no se le pone default=True a propósito.
    external_id = Column(String, nullable=True)
    moneda = Column(String, nullable=True)
    disponible = Column(Boolean, nullable=True)

    historial = relationship("HistorialPrecio", back_populates="producto")
    ofertas = relationship("Oferta", back_populates="producto")
    wishlist_items = relationship("WishlistItem", back_populates="producto")


class HistorialPrecio(Base):
    __tablename__ = "historial_precios"
    __table_args__ = (
        Index("ix_historial_precios_producto_fecha", "producto_id", "fecha"),
    )

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"))
    precio = Column(Float)
    fecha = Column(DateTime, default=datetime.utcnow)
    # NUEVO: nullable=True durante la transición - el historial existente no
    # tiene moneda y las integraciones todavía no la proveen consistentemente.
    moneda = Column(String, nullable=True)

    producto = relationship("Producto", back_populates="historial")


class Oferta(Base):
    __tablename__ = "ofertas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"))
    precio_actual = Column(Float)
    precio_promedio = Column(Float)
    descuento = Column(Float)
    fecha_detectada = Column(DateTime, default=datetime.utcnow)

    producto = relationship("Producto", back_populates="ofertas")


# NUEVO: tabla para guardar tokens de dispositivos
class PushToken(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    plataforma = Column(String)  # 'ios' o 'android'
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    activo = Column(Boolean, default=True)
    # nullable=True temporalmente: puede haber tokens legados sin dueño hasta migrar push.py
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), index=True, nullable=True)

    usuario = relationship("Usuario", back_populates="push_tokens")


# NUEVO: registro de notificaciones enviadas (para no spamear)
class NotificacionEnviada(Base):
    __tablename__ = "notificaciones_enviadas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"))
    token_id = Column(Integer, ForeignKey("push_tokens.id"))
    precio_notificado = Column(Float)
    fecha = Column(DateTime, default=datetime.utcnow)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Incrementar invalida de inmediato todos los access JWT emitidos
    # previamente (se compara contra el claim "ver" en get_usuario_actual).
    token_version = Column(Integer, nullable=False, default=1, server_default="1")

    wishlist_items = relationship(
        "WishlistItem", back_populates="usuario", cascade="all, delete-orphan"
    )
    push_tokens = relationship(
        "PushToken", back_populates="usuario", cascade="all, delete-orphan"
    )
    refresh_tokens = relationship(
        "RefreshToken", back_populates="usuario", cascade="all, delete-orphan"
    )
    password_reset_tokens = relationship(
        "PasswordResetToken", back_populates="usuario", cascade="all, delete-orphan"
    )


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint("usuario_id", "producto_id", name="uq_wishlist_usuario_producto"),
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    precio_al_agregar = Column(Float, nullable=False)
    fecha_agregado = Column(DateTime, default=datetime.utcnow, nullable=False)

    usuario = relationship("Usuario", back_populates="wishlist_items")
    producto = relationship("Producto", back_populates="wishlist_items")


# NUEVO: refresh tokens para renovación de sesión (Fase 2). Solo la
# estructura de datos por ahora: no se genera ni se hashea nada todavía
# desde aquí. El token en sí NUNCA se guarda en texto plano, solo su
# SHA-256 en token_hash.
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_expiracion = Column(DateTime, nullable=False)
    revocado = Column(Boolean, default=False, nullable=False)
    # Opcional: para auditar cuándo se invalidó una sesión (logout, reset de password, etc.)
    fecha_revocacion = Column(DateTime, nullable=True)

    usuario = relationship("Usuario", back_populates="refresh_tokens")


# NUEVO: tokens de recuperación de contraseña (Fase 2). Solo la estructura
# de datos por ahora: no se genera ni se hashea nada todavía desde aquí,
# ni hay endpoints ni envío de correo. El token en sí NUNCA se guarda en
# texto plano, solo su SHA-256 en token_hash.
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_expiracion = Column(DateTime, nullable=False)
    usado = Column(Boolean, default=False, nullable=False)
    # Para auditar cuándo se consumió el token
    fecha_uso = Column(DateTime, nullable=True)

    usuario = relationship("Usuario", back_populates="password_reset_tokens")