from app.productos import PRODUCTOS
from app.scrapers.ebay import scraper_ebay
from app.scrapers.etsy import scraper_etsy
from app.services.precios import obtener_precio_promedio, guardar_precio
from app.database import SessionLocal, engine
from app import models
from app.models import Producto, Oferta
from sqlalchemy.orm import Session
from datetime import datetime

DESCUENTO_MINIMO = 5.0  # % minimo para considerar oferta

# Lista de scrapers disponibles (nombre_mostrar, funcion_scraper)
SCRAPERS = [
    ("eBay", scraper_ebay),
    ("Etsy", scraper_etsy),
]


def guardar_oferta_db(db: Session, item: dict, precio_promedio: float, descuento: float, categoria: str):
    producto = db.query(Producto).filter(Producto.url == item["link"]).first()
    if not producto:
        producto = Producto(
            nombre=item["titulo"],
            url=item["link"],
            imagen_url=item.get("imagen"),
            tienda=item.get("tienda", "mercadolibre"),
            categoria=categoria,
            precio_actual=item["precio"],
            precio_original=precio_promedio,
            fecha_actualizacion=datetime.utcnow(),
        )
        db.add(producto)
        db.flush()
    else:
        # Actualizar precio actual del producto existente
        producto.precio_actual = item["precio"]
        producto.precio_original = precio_promedio
        producto.fecha_actualizacion = datetime.utcnow()

    guardar_precio(db, producto.id, item["precio"])

    ultima_oferta = (
        db.query(Oferta)
        .filter(Oferta.producto_id == producto.id)
        .order_by(Oferta.fecha_detectada.desc())
        .first()
    )

    if not ultima_oferta or round(ultima_oferta.precio_actual, 2) != round(item["precio"], 2):
        oferta = Oferta(
            producto_id=producto.id,
            precio_actual=item["precio"],
            precio_promedio=precio_promedio,
            descuento=descuento,
        )
        db.add(oferta)

    db.commit()


def guardar_precio_nuevo(db: Session, item: dict, categoria: str):
    """Registra un producto nuevo con su primer precio historico."""
    producto = Producto(
        nombre=item["titulo"],
        url=item["link"],
        imagen_url=item.get("imagen"),
        tienda=item.get("tienda", "mercadolibre"),
        categoria=categoria,
        precio_actual=item["precio"],
        fecha_actualizacion=datetime.utcnow(),
    )
    db.add(producto)
    db.flush()
    guardar_precio(db, producto.id, item["precio"])
    db.commit()


def procesar_resultados(db: Session, resultados: list, categoria: str):
    """Procesa los resultados de cualquier scraper y detecta ofertas."""
    for item in resultados:
        precio = item.get("precio", 0)
        precio_original_item = item.get("precio_original")

        if precio <= 0:
            continue

        producto_db = db.query(Producto).filter(Producto.url == item["link"]).first()

        # Prioridad 1: promedio historico real (cuando haya varias lecturas)
        promedio_historico = None
        if producto_db:
            promedio_historico = obtener_precio_promedio(db, producto_db.id, dias=14)

        # Decidir que usar como "precio de referencia"
        if promedio_historico and promedio_historico > precio:
            # Usar historico real
            promedio = promedio_historico
            fuente = "historico"
        elif precio_original_item and precio_original_item > precio:
            # Usar precio original/tachado del producto
            promedio = precio_original_item
            fuente = f"{item['tienda']}-tachado"
            if not producto_db:
                guardar_precio_nuevo(db, item, categoria)
        else:
            # Fallback: sin oferta detectable, solo registrar precio
            if not producto_db:
                guardar_precio_nuevo(db, item, categoria)
            else:
                guardar_precio(db, producto_db.id, precio)
                # Actualizar precio actual del producto aunque no sea oferta
                producto_db.precio_actual = precio
                producto_db.fecha_actualizacion = datetime.utcnow()
                db.commit()
            print(f"  Producto: {item['titulo'][:50]}")
            print(f"  Precio: ${precio:,.2f} (sin precio de referencia, no es oferta)\n")
            continue

        descuento = ((promedio - precio) / promedio) * 100

        print(f"  Producto: {item['titulo'][:50]}")
        print(f"  Precio: ${precio:,.2f} | Antes: ${promedio:,.2f} | Descuento: {descuento:.1f}% ({fuente}) | Tienda: {item['tienda']}")

        if descuento >= DESCUENTO_MINIMO:
            print(f"  OFERTA DETECTADA\n")
            guardar_oferta_db(db, item, promedio, descuento, categoria)
        else:
            if producto_db:
                guardar_precio(db, producto_db.id, precio)
                producto_db.precio_actual = precio
                producto_db.fecha_actualizacion = datetime.utcnow()
                db.commit()
            print()


def detectar_ofertas():
    """Funcion principal que se llama desde el scheduler."""
    ejecutar()


def ejecutar():
    # Crear las tablas si no existen
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        for producto_cfg in PRODUCTOS:
            nombre = producto_cfg["nombre"]
            categoria = producto_cfg.get("categoria", "general")
            print(f"\n{'='*60}")
            print(f"Buscando: {nombre.upper()} en todas las tiendas")
            print(f"{'='*60}")

            for nombre_tienda, scraper in SCRAPERS:
                print(f"\n  [{nombre_tienda}] Buscando '{nombre}'...")
                try:
                    resultados = scraper(nombre)
                except Exception as e:
                    print(f"  [{nombre_tienda}] Error al buscar {nombre}: {e}")
                    continue

                if not resultados:
                    print(f"  [{nombre_tienda}] Sin resultados")
                    continue

                print(f"  [{nombre_tienda}] {len(resultados)} resultado(s)")
                procesar_resultados(db, resultados, categoria)

    finally:
        db.close()


if __name__ == "__main__":
    ejecutar()
