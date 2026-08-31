"""
Endpoint para obtener detalle completo de un producto
incluyendo historial de precios y estadísticas.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import Producto, HistorialPrecio

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

    # Obtener historial de los últimos 30 días
    hace_30_dias = datetime.utcnow() - timedelta(days=30)
    historial = db.query(HistorialPrecio).filter(
        HistorialPrecio.producto_id == producto_id,
        HistorialPrecio.fecha >= hace_30_dias,
        HistorialPrecio.precio != None,
    ).order_by(HistorialPrecio.fecha.asc()).all()

    # Armar lista de precios (filtrar None)
    precios_historico = [
        {"fecha": h.fecha.isoformat(), "precio": h.precio}
        for h in historial
        if h.precio is not None
    ]

    # Calcular estadísticas solo con valores válidos
    precios_valores = [h.precio for h in historial if h.precio is not None]
    if not precios_valores and precio_actual > 0:
        precios_valores = [precio_actual]

    if precios_valores:
        precio_min = min(precios_valores)
        precio_max = max(precios_valores)
        precio_promedio = sum(precios_valores) / len(precios_valores)
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
        "en_wishlist": producto.en_wishlist,
        "historial": precios_historico,
        "estadisticas": {
            "precio_minimo": precio_min,
            "precio_maximo": precio_max,
            "precio_promedio": round(precio_promedio, 2),
            "es_minimo_historico": es_minimo_historico,
            "porcentaje_vs_promedio": round(porcentaje_vs_promedio, 1),
            "total_registros": len(precios_historico),
        },
    }