from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from typing import Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Oferta, Producto
from app.services.precios import TOLERANCIA_VIGENCIA_HORAS
from app import schemas  # lo creamos después

router = APIRouter(prefix="/ofertas")

@router.get("/", response_model=list[schemas.OfertaResponse])
def listar_ofertas(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    tienda: Optional[str] = Query(None, description="Filtrar por tienda"),
    descuento_minimo: float = Query(10.0, description="Descuento mínimo en %"),
    skip: int = Query(0, description="Paginación: desde"),
    limit: int = Query(20, description="Paginación: hasta"),
    db: Session = Depends(get_db)
):
    limite_vigencia = datetime.utcnow() - timedelta(hours=TOLERANCIA_VIGENCIA_HORAS)

    # Vigente solo si el precio de la oferta coincide (tolerancia de
    # centavos, portable entre SQLite y PostgreSQL) con el precio actual
    # del producto, y el producto fue observado dentro de la tolerancia de
    # vigencia. No basta con filtrar por Oferta.fecha_detectada: el dedupe
    # existente (guardar_oferta_db) no crea una fila nueva mientras el
    # precio no cambie, así que una oferta vigente puede arrastrar una
    # fecha_detectada antigua aunque el producto se siga observando al
    # mismo precio en cada corrida del scheduler. Se filtra a nivel SQL
    # (no en Python) para que offset/limit paginen sobre el conjunto ya
    # vigente y no se pierdan filas por descartar registros no vigentes
    # después de recortar la página.
    query = (
        db.query(Oferta)
        .join(Producto)
        .options(joinedload(Oferta.producto))
        .filter(
            Producto.fecha_actualizacion >= limite_vigencia,
            Producto.precio_actual.isnot(None),
            func.abs(Oferta.precio_actual - Producto.precio_actual) < 0.005,
        )
    )

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
            "fecha_detectada": o.fecha_detectada,
        }
        for o in ofertas
    ]