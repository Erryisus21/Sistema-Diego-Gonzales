# app/schemas.py
from pydantic import BaseModel
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