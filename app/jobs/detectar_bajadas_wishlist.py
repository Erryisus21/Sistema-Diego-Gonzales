"""
Job que revisa productos en wishlist y envía notificaciones
cuando el precio ha bajado >=10% desde que se agregaron.
"""
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Producto, PushToken, NotificacionEnviada
from app.services.notificaciones import enviar_notificacion
from datetime import datetime, timedelta

# Umbral mínimo de descuento para notificar (10%)
UMBRAL_DESCUENTO = 10.0

# Evitar notificar el mismo producto más de una vez cada X horas
COOLDOWN_HORAS = 24


def detectar_bajadas():
    """Revisa cada producto en wishlist y notifica si bajó significativamente."""
    db: Session = SessionLocal()

    try:
        # Obtener productos en wishlist con precio registrado al agregar
        productos_wishlist = db.query(Producto).filter(
            Producto.en_wishlist == True,
            Producto.precio_al_agregar_wishlist != None,
            Producto.precio_al_agregar_wishlist > 0,
        ).all()

        print(f"[WISHLIST] Revisando {len(productos_wishlist)} productos...")

        if not productos_wishlist:
            return

        # Obtener todos los tokens activos
        tokens_activos = db.query(PushToken).filter(PushToken.activo == True).all()

        if not tokens_activos:
            print("[WISHLIST] No hay dispositivos registrados, saltando...")
            return

        notificaciones_enviadas = 0

        for producto in productos_wishlist:
            precio_anterior = producto.precio_al_agregar_wishlist
            precio_actual = producto.precio_actual

            if precio_actual >= precio_anterior:
                continue  # No bajó, o subió

            # Calcular porcentaje de bajada
            descuento = ((precio_anterior - precio_actual) / precio_anterior) * 100

            if descuento < UMBRAL_DESCUENTO:
                continue  # Bajada muy pequeña

            # Para cada token, verificar si no se ha notificado recientemente
            for token in tokens_activos:
                hace_24h = datetime.utcnow() - timedelta(hours=COOLDOWN_HORAS)
                notificacion_reciente = db.query(NotificacionEnviada).filter(
                    NotificacionEnviada.producto_id == producto.id,
                    NotificacionEnviada.token_id == token.id,
                    NotificacionEnviada.fecha > hace_24h,
                ).first()

                if notificacion_reciente:
                    continue  # Ya se notificó recientemente

                # Preparar mensaje
                nombre_corto = producto.nombre[:50] + "..." if len(producto.nombre) > 50 else producto.nombre
                titulo = f"¡Bajó de precio! -{int(descuento)}%"
                mensaje = f"{nombre_corto} - Ahora ${int(precio_actual):,} (antes ${int(precio_anterior):,})"

                # Enviar
                enviado = enviar_notificacion(
                    token=token.token,
                    titulo=titulo,
                    mensaje=mensaje,
                    data={"producto_id": producto.id, "url": producto.url},
                )

                if enviado:
                    # Registrar notificación enviada
                    registro = NotificacionEnviada(
                        producto_id=producto.id,
                        token_id=token.id,
                        precio_notificado=precio_actual,
                    )
                    db.add(registro)
                    notificaciones_enviadas += 1
                else:
                    # Token inválido, desactivarlo
                    token.activo = False

        db.commit()
        print(f"[WISHLIST] Notificaciones enviadas: {notificaciones_enviadas}")

    except Exception as e:
        print(f"[WISHLIST] Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    detectar_bajadas()