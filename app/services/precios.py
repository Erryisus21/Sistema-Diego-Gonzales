from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.models import HistorialPrecio, Producto

def obtener_precio_promedio(
    db: Session,
    producto_id: int,
    dias: int = 14
) -> float | None:
    desde = datetime.utcnow() - timedelta(days=dias)

    resultado = db.query(func.avg(HistorialPrecio.precio)).filter(
        HistorialPrecio.producto_id == producto_id,
        HistorialPrecio.fecha >= desde
    ).scalar()

    return float(resultado) if resultado else None


def _normalizar_moneda(moneda: str | None) -> str | None:
    if moneda is None:
        return None
    moneda = moneda.strip().upper()
    return moneda or None


def guardar_precio(db: Session, producto_id: int, precio: float, moneda: str | None = None):
    """Registra un nuevo HistorialPrecio, salvo que sea idéntico al último
    (mismo precio redondeado y misma moneda) para ese producto, evitando
    duplicados consecutivos sin perder cambios reales.

    No hace commit(): el llamador conserva el manejo transaccional actual.
    """
    moneda_normalizada = _normalizar_moneda(moneda)

    ultimo = (
        db.query(HistorialPrecio)
        .filter(HistorialPrecio.producto_id == producto_id)
        .order_by(HistorialPrecio.fecha.desc())
        .first()
    )

    if ultimo:
        moneda_ultimo = _normalizar_moneda(ultimo.moneda)
        mismo_precio = round(ultimo.precio, 2) == round(precio, 2)
        misma_moneda = moneda_ultimo == moneda_normalizada
        if mismo_precio and misma_moneda:
            return  # sin cambios reales, no duplicar

    registro = HistorialPrecio(
        producto_id=producto_id,
        precio=precio,
        moneda=moneda_normalizada,
    )
    db.add(registro)