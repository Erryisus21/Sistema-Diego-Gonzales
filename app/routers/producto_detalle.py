"""
Endpoint para obtener detalle completo de un producto
incluyendo historial de precios y estadísticas.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Producto
from app.services.precios import obtener_estadisticas_precio

router = APIRouter(prefix="/producto", tags=["producto"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{producto_id}")
def obtener_detalle(producto_id: int, db: Session = Depends(get_db)):
    """Devuelve detalle completo del producto con historial de precios."""
    producto = db.query(Producto).filter(Producto.id == producto_id).first()

    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # Precio actual con fallback
    precio_actual = producto.precio_actual or 0

    # Estadísticas de los últimos 30 días, sin mezclar monedas distintas
    stats = obtener_estadisticas_precio(db, producto_id, dias=30, moneda=producto.moneda)
    precios_historico = stats["historial"]

    # Calcular estadísticas: usar las del historial si hay registros
    # compatibles, o caer al precio_actual del producto si no hay ninguno.
    if stats["total_registros"] > 0:
        precio_min = stats["precio_minimo"]
        precio_max = stats["precio_maximo"]
        precio_promedio = stats["precio_promedio"]
    else:
        precio_min = precio_actual
        precio_max = precio_actual
        precio_promedio = precio_actual

    # Determinar si el precio actual es bueno
    es_minimo_historico = precio_actual > 0 and precio_actual <= precio_min
    porcentaje_vs_promedio = (
        ((precio_promedio - precio_actual) / precio_promedio * 100)
        if precio_promedio > 0 else 0
    )

    return {
        "id": producto.id,
        "nombre": producto.nombre,
        "url": producto.url,
        "imagen_url": producto.imagen_url,
        "tienda": producto.tienda,
        "categoria": producto.categoria,
        "precio_actual": precio_actual,
        "precio_original": producto.precio_original,
        "historial": precios_historico,
        "estadisticas": {
            "precio_minimo": precio_min,
            "precio_maximo": precio_max,
            "precio_promedio": round(precio_promedio, 2),
            "es_minimo_historico": es_minimo_historico,
            "porcentaje_vs_promedio": round(porcentaje_vs_promedio, 1),
            "total_registros": stats["total_registros"],
        },
    }
