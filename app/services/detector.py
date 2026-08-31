from sqlalchemy.orm import Session
from app.models import Oferta, Producto

DESCUENTO_MINIMO = 20.0  # % mínimo para considerar oferta

def detectar_oferta(
    db: Session,
    producto_id: int,
    precio_actual: float,
    precio_promedio: float,
) -> dict | None:

    if precio_promedio <= 0 or precio_actual <= 0:
        return None

    descuento = round(
        (precio_promedio - precio_actual) / precio_promedio * 100, 2
    )

    if descuento < DESCUENTO_MINIMO:
        return None

    # Evitar duplicados — si ya hay oferta activa para este producto
    existente = db.query(Oferta).filter(
        Oferta.producto_id == producto_id,
        Oferta.activa == True
    ).first()

    if existente:
        # Actualizar precio si cambió
        if existente.precio_actual != precio_actual:
            existente.precio_actual = precio_actual
            existente.descuento = descuento
            db.commit()
        return {"status": "ya_existe", "oferta_id": existente.id}

    oferta = Oferta(
        producto_id=producto_id,
        precio_actual=precio_actual,
        precio_promedio=precio_promedio,
        descuento=descuento,
        activa=True,
    )