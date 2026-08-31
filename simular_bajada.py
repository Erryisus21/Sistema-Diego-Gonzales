"""
Script de prueba: simula que bajó el precio de productos en wishlist
para disparar las notificaciones locales en el frontend.
"""
from app.database import SessionLocal
from app.models import Producto


def simular_bajada_wishlist(porcentaje_bajada=30):
    """
    Reduce el precio_actual de todos los productos en wishlist
    en el porcentaje especificado.
    """
    db = SessionLocal()
    try:
        productos = db.query(Producto).filter(Producto.en_wishlist == True).all()

        if not productos:
            print("❌ No hay productos en wishlist. Agrega uno desde la app primero.")
            return

        print(f"🎯 Simulando bajada del {porcentaje_bajada}% en {len(productos)} producto(s):\n")

        for p in productos:
            precio_anterior = p.precio_actual
            nuevo_precio = precio_anterior * (1 - porcentaje_bajada / 100)
            p.precio_actual = nuevo_precio

            # Asegurar que precio_al_agregar_wishlist esté puesto
            if not p.precio_al_agregar_wishlist:
                p.precio_al_agregar_wishlist = precio_anterior

            print(f"  📦 {p.nombre[:50]}")
            print(f"     Antes: ${precio_anterior:,.2f}")
            print(f"     Ahora: ${nuevo_precio:,.2f}")
            print(f"     Bajada: -{porcentaje_bajada}%\n")

        db.commit()
        print("✅ Precios actualizados. Abre la app para ver la notificación.")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    simular_bajada_wishlist(porcentaje_bajada=30)