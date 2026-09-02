"""
Job que revisa los WishlistItem de todos los usuarios y envía notificaciones
cuando el precio de un producto ha bajado >=10% desde que se agregó.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models import WishlistItem, PushToken, NotificacionEnviada
from app.services.notificaciones import enviar_notificacion

# Umbral mínimo de descuento para notificar (10%)
UMBRAL_DESCUENTO = 10.0

# Evitar notificar el mismo producto más de una vez cada X horas
COOLDOWN_HORAS = 24


def detectar_bajadas():
    """Revisa cada WishlistItem y notifica al dueño si el producto bajó significativamente."""
    db: Session = SessionLocal()

    try:
        items = (
            db.query(WishlistItem)
            .options(joinedload(WishlistItem.producto))
            .all()
        )

        print(f"[WISHLIST] Revisando {len(items)} items de wishlist...")

        if not items:
            return

        notificaciones_enviadas = 0
        tokens_por_usuario: dict[int, list[PushToken]] = {}

        for item in items:
            producto = item.producto
            precio_anterior = item.precio_al_agregar
            precio_actual = producto.precio_actual if producto else None

            if (
                not producto
                or precio_anterior is None
                or precio_actual is None
                or precio_anterior <= 0
                or precio_actual <= 0
                or precio_actual >= precio_anterior
            ):
                continue  # datos incompletos, o no bajó / subió

            # Calcular porcentaje de bajada
            descuento = ((precio_anterior - precio_actual) / precio_anterior) * 100

            if descuento < UMBRAL_DESCUENTO:
                continue  # bajada muy pequeña

            # Tokens activos de este usuario, cacheados para no repetir la
            # consulta si tiene varios productos calificando en esta corrida.
            if item.usuario_id not in tokens_por_usuario:
                tokens_por_usuario[item.usuario_id] = db.query(PushToken).filter(
                    PushToken.activo == True,
                    PushToken.usuario_id == item.usuario_id,
                ).all()

            tokens_usuario = tokens_por_usuario[item.usuario_id]

            if not tokens_usuario:
                continue  # este usuario no tiene dispositivos; seguir con el resto

            # Para cada token del usuario, verificar si no se ha notificado recientemente
            for token in tokens_usuario:
                if not token.activo:
                    continue  # ya se desactivó en esta misma corrida, no reintentar

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

                if enviado is True:
                    # Registrar notificación enviada y persistir de inmediato:
                    # Expo aceptó/procesó correctamente el envío, no hay forma
                    # de deshacer ese efecto, así que este registro no debe
                    # depender de que el resto de la corrida termine bien.
                    registro = NotificacionEnviada(
                        producto_id=producto.id,
                        token_id=token.id,
                        precio_notificado=precio_actual,
                    )
                    db.add(registro)
                    try:
                        db.commit()
                        notificaciones_enviadas += 1
                    except Exception as e:
                        db.rollback()
                        # No hay atomicidad con Expo: Expo ya aceptó/procesó el
                        # envío pero no pudimos registrarlo. Puede reenviarse
                        # en la próxima corrida. No exponemos el token, solo el id.
                        print(
                            f"[WISHLIST] Error guardando NotificacionEnviada "
                            f"(producto_id={producto.id}, token_id={token.id}, "
                            f"posible reenvío futuro): {type(e).__name__}: {e}"
                        )

                elif enviado is False:
                    # Token definitivamente inválido: desactivar y persistir
                    # de inmediato, sin esperar al resto de la corrida.
                    token.activo = False
                    try:
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        print(
                            f"[WISHLIST] Error guardando desactivación de token "
                            f"(token_id={token.id}): {type(e).__name__}: {e}"
                        )

                # enviado is None: error temporal/inesperado -> no se registra
                # NotificacionEnviada (sin cooldown falso), no se desactiva el
                # token, y no hay nada que commitear.

        print(f"[WISHLIST] Notificaciones enviadas: {notificaciones_enviadas}")

    except Exception as e:
        print(f"[WISHLIST] Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    detectar_bajadas()
