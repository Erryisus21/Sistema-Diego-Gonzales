from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Producto, Oferta
from app import schemas

router = APIRouter(prefix="/busqueda")

@router.get("/", response_model=list[schemas.OfertaResponse])
def buscar_ofertas(
    q: str = Query(..., description="Término de búsqueda"),
    db: Session = Depends(get_db)
):
    resultados = db.query(Oferta).join(Producto).filter(
        or_(
            Producto.nombre.ilike(f"%{q}%"),
            Producto.categoria.ilike(f"%{q}%"),
            Producto.tienda.ilike(f"%{q}%")
        )
    ).order_by(Oferta.descuento.desc()).limit(50).all()

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
        for o in resultados
    ]