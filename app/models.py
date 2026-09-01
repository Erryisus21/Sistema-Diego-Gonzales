from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint
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
    en_wishlist = Column(Boolean, default=False)
    # NUEVO: precio al que se agregó a wishlist (para comparar bajadas)
    precio_al_agregar_wishlist = Column(Float, nullable=True)

    historial = relationship("HistorialPrecio", back_populates="producto")
    ofertas = relationship("Oferta", back_populates="producto")
    wishlist_items = relationship("WishlistItem", back_populates="producto")


class HistorialPrecio(Base):
    __tablename__ = "historial_precios"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"))
    precio = Column(Float)
    fecha = Column(DateTime, default=datetime.utcnow)

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

    wishlist_items = relationship(
        "WishlistItem", back_populates="usuario", cascade="all, delete-orphan"
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