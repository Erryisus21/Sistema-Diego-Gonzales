from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, desc
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
    #
    # Producto.disponible.isnot(False) excluye únicamente los productos
    # marcados explícitamente como no disponibles; los legacy/actuales con
    # disponible=None siguen visibles mientras cumplan las demás reglas de
    # vigencia (regla de transición mientras no todas las integraciones
    # reporten disponibilidad).
    # SOLO condiciones que determinan si una fila de Oferta representa el
    # estado REAL vigente del producto (ver comentario detallado en
    # GET /ofertas). La búsqueda textual es un filtro de presentación y se
    # aplica DESPUÉS de la deduplicación, no aquí: si entrara aquí, una
    # fila histórica más antigua del mismo producto podría "ganar" el
    # ranking solo por coincidir con el texto de forma distinta a la
    # oferta realmente vigente (aunque en la práctica nombre/categoria/
    # tienda no cambian entre filas del mismo producto, se mantiene la
    # misma separación de responsabilidades que en /ofertas).
    condiciones_vigencia = [
        Producto.fecha_actualizacion >= limite_vigencia,
        Producto.precio_actual.isnot(None),
        func.abs(Oferta.precio_actual - Producto.precio_actual) < 0.005,
        Producto.disponible.isnot(False),
    ]

    # row_number() (portable entre SQLite y PostgreSQL): una sola fila por
    # producto_id, la de fecha_detectada más reciente (id DESC de
    # desempate), ANTES de aplicar la búsqueda textual, ordenar o limitar.
    ranking = (
        db.query(
            Oferta.id.label("oferta_id"),
            func.row_number()
            .over(
                partition_by=Oferta.producto_id,
                order_by=(desc(Oferta.fecha_detectada), desc(Oferta.id)),
            )
            .label("rn"),
        )
        .join(Producto, Oferta.producto_id == Producto.id)
        .filter(*condiciones_vigencia)
        .subquery()
    )

    resultados = (
        db.query(Oferta)
        .join(Producto)
        .options(joinedload(Oferta.producto))
        .join(ranking, ranking.c.oferta_id == Oferta.id)
        .filter(ranking.c.rn == 1)
        .filter(
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