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
    #
    # Producto.disponible.isnot(False) excluye únicamente los productos
    # marcados explícitamente como no disponibles; los legacy/actuales con
    # disponible=None (sin dato, porque la fuente no lo informa) siguen
    # visibles mientras cumplan las demás reglas de vigencia — regla de
    # transición mientras no todas las integraciones reporten disponibilidad.
    # SOLO las condiciones que determinan si una fila de Oferta representa
    # el estado REAL vigente del producto ahora mismo. Deliberadamente NO
    # incluye filtros de presentación (descuento_minimo, categoria, tienda):
    # si esos entraran aquí, una fila histórica más antigua podría "ganar"
    # el ranking solo porque cumple un filtro que la oferta realmente
    # vigente (la más reciente) no cumple -- p. ej. la vigente bajó a 10%
    # de descuento pero una vieja tenía 40%; con descuento_minimo=20 la
    # vieja no debe "resucitar" solo por pasar ese filtro en la subconsulta.
    condiciones_vigencia = [
        Producto.fecha_actualizacion >= limite_vigencia,
        Producto.precio_actual.isnot(None),
        func.abs(Oferta.precio_actual - Producto.precio_actual) < 0.005,
        Producto.disponible.isnot(False),
    ]

    # Entre las filas vigentes de arriba puede haber más de una para el
    # mismo producto: la deduplicación de eventos en guardar_oferta_db
    # permite intencionalmente un segundo evento de Oferta aunque su precio
    # coincida con uno histórico (p. ej. baja->sube->misma baja), y ambas
    # filas pueden coincidir con Producto.precio_actual al mismo tiempo.
    # row_number() (portable entre SQLite 3.25+ y PostgreSQL) numera las
    # filas vigentes de cada producto_id de más reciente a más antigua
    # (fecha_detectada DESC, id DESC como desempate determinista) y solo
    # nos quedamos con la #1 de cada producto, ANTES de aplicar filtros de
    # presentación, ordenar o paginar.
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

    # A partir de aquí, exactamente una fila de Oferta por producto (la
    # vigente más reciente). Los filtros de presentación se aplican DESPUÉS
    # de la deduplicación, sobre esa única fila: si no cumple, el producto
    # simplemente no aparece (no se sustituye por una fila vieja distinta).
    query = (
        db.query(Oferta)
        .join(Producto)
        .options(joinedload(Oferta.producto))
        .join(ranking, ranking.c.oferta_id == Oferta.id)
        .filter(ranking.c.rn == 1)
        .filter(Oferta.descuento >= descuento_minimo)
    )

    if categoria:
        query = query.filter(Producto.categoria == categoria)
    if tienda:
        query = query.filter(Producto.tienda == tienda)

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