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


def enviar_notificacion(token: str, titulo: str, mensaje: str, data: dict = None) -> bool | None:
    """
    Envía una notificación push a un token específico.

    Retorna:
        True  -> envío confirmado por Expo.
        False -> el token ya no es válido (DeviceNotRegisteredError), debe desactivarse.
        None  -> error temporal o inesperado; no se sabe si se entregó, no
                 debe tratarse como éxito ni como token inválido.
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
        print(f"  ✗ Error de servidor Expo (temporal): {e}")
        return None  # Reintentar después, no invalidar token

    except PushTicketError as e:
        print(f"  ✗ Error en ticket (temporal): {e}")
        return None

    except Exception as e:
        # Cualquier otro error no previsto: no debe tumbar al llamador ni
        # exponer el token, el mensaje completo de la excepción ni datos
        # sensibles, solo el tipo de error.
        print(f"  ✗ Error inesperado enviando notificación: {type(e).__name__}")
        return None


def enviar_notificacion_multiple(tokens: list, titulo: str, mensaje: str, data: dict = None):
    """
    Envía la misma notificación a múltiples tokens.
    Retorna lista de tokens inválidos (resultado is False) que deben
    marcarse como inactivos. Un resultado None (error temporal) no se
    considera inválido.
    """
    tokens_invalidos = []
    for token in tokens:
        resultado = enviar_notificacion(token, titulo, mensaje, data)
        if resultado is False:
            tokens_invalidos.append(token)
    return tokens_invalidos