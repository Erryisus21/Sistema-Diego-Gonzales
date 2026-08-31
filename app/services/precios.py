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
        HistorialPrecio.registrado_en >= desde
    ).scalar()

    return float(resultado) if resultado else None


def guardar_precio(db: Session, producto_id: int, precio: float):
    registro = HistorialPrecio(producto_id=producto_id, precio=precio)
    db.add(registro)
    db.commit()