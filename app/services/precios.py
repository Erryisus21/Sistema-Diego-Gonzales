from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import HistorialPrecio

def _normalizar_moneda(moneda: str | None) -> str | None:
    if moneda is None:
        return None
    moneda = moneda.strip().upper()
    return moneda or None


def obtener_estadisticas_precio(
    db: Session,
    producto_id: int,
    dias: int = 30,
    moneda: str | None = None,
) -> dict:
    """Fuente de verdad centralizada para estadísticas de HistorialPrecio.

    Consulta los registros del producto dentro de la ventana de `dias` y
    calcula precio_minimo, precio_maximo, precio_promedio, total_registros
    y la serie cronológica ("historial") usada en el detalle del producto.

    La moneda se normaliza con la misma regla que guardar_precio()
    (strip().upper()). Para no mezclar monedas distintas en una misma
    estadística: si `moneda` es None, solo se usan registros cuyo
    HistorialPrecio.moneda IS NULL; si `moneda` no es None, solo se usan
    registros con esa moneda exacta (ya normalizada).

    Si no hay registros compatibles, devuelve estadísticas vacías de forma
    controlada (los tres precios en None, total_registros en 0, historial
    en []) para que el llamador decida su propio fallback.
    """
    moneda_normalizada = _normalizar_moneda(moneda)
    desde = datetime.utcnow() - timedelta(days=dias)

    query = db.query(HistorialPrecio).filter(
        HistorialPrecio.producto_id == producto_id,
        HistorialPrecio.fecha >= desde,
        HistorialPrecio.precio != None,
    )
    if moneda_normalizada is None:
        query = query.filter(HistorialPrecio.moneda.is_(None))
    else:
        query = query.filter(HistorialPrecio.moneda == moneda_normalizada)

    registros = query.order_by(HistorialPrecio.fecha.asc()).all()

    if not registros:
        return {
            "precio_minimo": None,
            "precio_maximo": None,
            "precio_promedio": None,
            "total_registros": 0,
            "historial": [],
        }

    historial = [{"fecha": r.fecha.isoformat(), "precio": r.precio} for r in registros]
    precios = [r.precio for r in registros]

    return {
        "precio_minimo": min(precios),
        "precio_maximo": max(precios),
        "precio_promedio": sum(precios) / len(precios),
        "total_registros": len(precios),
        "historial": historial,
    }


def obtener_precio_promedio(
    db: Session,
    producto_id: int,
    dias: int = 14,
    moneda: str | None = None,
) -> float | None:
    """Wrapper compatible sobre obtener_estadisticas_precio(): solo el
    precio_promedio dentro de la ventana de `dias`, sin mezclar monedas."""
    return obtener_estadisticas_precio(db, producto_id, dias=dias, moneda=moneda)["precio_promedio"]


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