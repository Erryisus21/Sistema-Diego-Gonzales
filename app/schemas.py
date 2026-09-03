# app/schemas.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class OfertaResponse(BaseModel):
    id: int
    producto: str
    categoria: str
    tienda: str
    imagen_url: str | None
    url: str
    precio_actual: float
    precio_promedio: float
    descuento: float
    fecha_detectada: datetime

    class Config:
        from_attributes = True


class UsuarioRegistro(BaseModel):
    nombre: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    activo: bool
    fecha_registro: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class LogoutResponse(BaseModel):
    mensaje: str


class WishlistItemResponse(BaseModel):
    id: int
    producto_id: int
    nombre: str
    url: str
    imagen_url: str | None
    tienda: str
    categoria: str | None
    precio_actual: float
    precio_original: float | None
    precio_al_agregar: float
    fecha_agregado: datetime

    class Config:
        from_attributes = True