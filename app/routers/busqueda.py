from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Producto
from app import schemas

router = APIRouter(prefix="/busqueda")


@router.get("/", response_model=list[schemas.ProductoCatalogoResponse])
def buscar_productos(
    q: str = Query(..., description="Término de búsqueda"),
    skip: int = Query(0, description="Paginación: desde"),
    limit: int = Query(50, description="Paginación: hasta"),
    db: Session = Depends(get_db),
):
    """Busca sobre el catálogo completo (Producto), no solo sobre ofertas
    vigentes: un producto sigue siendo encontrable aunque nunca haya tenido
    descuento, ya no lo tenga, o esté marcado disponible=False. Las reglas
    estrictas de vigencia (fecha_actualizacion reciente, coincidencia de
    precio, disponible != False) son responsabilidad exclusiva de
    GET /ofertas; /busqueda es el catálogo histórico y expone el estado
    real del producto (incluida su indisponibilidad) para que el frontend
    decida cómo mostrarlo, en vez de ocultarlo.

    Coincidencia case-insensitive (ilike) sobre nombre, categoria y tienda.
    Cada producto aparece una sola vez (no hay join contra Oferta que
    pudiera multiplicar filas). `url` se devuelve exactamente como fue
    almacenada -- nunca se reescribe ni se acorta -- para que la compra
    siga ocurriendo únicamente en el marketplace original.
    """
    productos = (
        db.query(Producto)
        .filter(
            or_(
                Producto.nombre.ilike(f"%{q}%"),
                Producto.categoria.ilike(f"%{q}%"),
                Producto.tienda.ilike(f"%{q}%"),
            )
        )
        .order_by(Producto.fecha_actualizacion.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": p.id,
            "external_id": p.external_id,
            "nombre": p.nombre,
            "url": p.url,
            "imagen_url": p.imagen_url,
            "tienda": p.tienda,
            "categoria": p.categoria,
            "precio_actual": p.precio_actual,
            "precio_original": p.precio_original,
            "moneda": p.moneda,
            "disponible": p.disponible,
            "fecha_actualizacion": p.fecha_actualizacion,
        }
        for p in productos
    ]
