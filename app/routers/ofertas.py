from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.database import get_db
from app.models import Oferta, Producto
from app import schemas  # lo creamos después

router = APIRouter()

@router.get("/", response_model=list[schemas.OfertaResponse])
def listar_ofertas(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    tienda: Optional[str] = Query(None, description="Filtrar por tienda"),
    descuento_minimo: float = Query(10.0, description="Descuento mínimo en %"),
    skip: int = Query(0, description="Paginación: desde"),
    limit: int = Query(20, description="Paginación: hasta"),
    db: Session = Depends(get_db)
):
    query = db.query(Oferta).join(Producto).filter(Oferta.activa == True)

    if categoria:
        query = query.filter(Producto.categoria == categoria)
    if tienda:
        query = query.filter(Producto.tienda == tienda)

    query = query.filter(Oferta.descuento >= descuento_minimo)
    query = query.order_by(desc(Oferta.descuento))

    ofertas = query.offset(skip).limit(limit).all()

    return [
        {
            "id": o.id,
            "producto": o.producto.nombre,
            "categoria": o.producto.categoria,
            "tienda": o.producto.tienda,
            "imagen_url": o.producto.imagen_url,
            "url": o.producto.url,
            "precio_actual": o.precio_actual,
            "precio_promedio": o.precio_promedio,
            "descuento": o.descuento,
            "es_relampago": o.es_relampago,
            "detectada_en": o.detectada_en,
        }
        for o in ofertas
    ]