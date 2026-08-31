"""
Servicio de envío de notificaciones push vía Expo.
"""
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from requests.exceptions import ConnectionError, HTTPError


def enviar_notificacion(token: str, titulo: str, mensaje: str, data: dict = None):
    """
    Envía una notificación push a un token específico.
    Retorna True si se envió correctamente, False si el token ya no es válido.
    """
    try:
        response = PushClient().publish(
            PushMessage(
                to=token,
                title=titulo,
                body=mensaje,
                data=data or {},
                sound="default",
                priority="high",
            )
        )
        response.validate_response()
        print(f"  ✓ Notificación enviada a {token[:30]}...")
        return True

    except DeviceNotRegisteredError:
        print(f"  ✗ Token no registrado (dispositivo desinstaló la app): {token[:30]}...")
        return False

    except (PushServerError, ConnectionError, HTTPError) as e:
        print(f"  ✗ Error de servidor Expo: {e}")
        return True  # Reintentar después, no invalidar token

    except PushTicketError as e:
        print(f"  ✗ Error en ticket: {e}")
        return True


def enviar_notificacion_multiple(tokens: list, titulo: str, mensaje: str, data: dict = None):
    """
    Envía la misma notificación a múltiples tokens.
    Retorna lista de tokens inválidos que deben marcarse como inactivos.
    """
    tokens_invalidos = []
    for token in tokens:
        valido = enviar_notificacion(token, titulo, mensaje, data)
        if not valido:
            tokens_invalidos.append(token)
    return tokens_invalidos