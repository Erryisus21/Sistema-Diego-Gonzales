from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Producto, Oferta
from app.services.precios import TOLERANCIA_VIGENCIA_HORAS
from app import schemas

router = APIRouter(prefix="/busqueda")

@router.get("/", response_model=list[schemas.OfertaResponse])
def buscar_ofertas(
    q: str = Query(..., description="Término de búsqueda"),
    db: Session = Depends(get_db)
):
    limite_vigencia = datetime.utcnow() - timedelta(hours=TOLERANCIA_VIGENCIA_HORAS)

    # Mismo criterio de vigencia que GET /ofertas (ver comentario allá):
    # precio_actual coincidente (tolerancia de centavos, a nivel SQL) y
    # producto observado dentro de la tolerancia de vigencia. Se filtra en
    # SQL, no en Python, para que el limit(50) recorte sobre el conjunto ya
    # vigente y no descarte filas después de haber limitado la página.
    resultados = (
        db.query(Oferta)
        .join(Producto)
        .options(joinedload(Oferta.producto))
        .filter(
            Producto.fecha_actualizacion >= limite_vigencia,
            Producto.precio_actual.isnot(None),
            func.abs(Oferta.precio_actual - Producto.precio_actual) < 0.005,
            or_(
                Producto.nombre.ilike(f"%{q}%"),
                Producto.categoria.ilike(f"%{q}%"),
                Producto.tienda.ilike(f"%{q}%")
            )
        )
        .order_by(Oferta.descuento.desc())
        .limit(50)
        .all()
    )

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