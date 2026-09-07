"""
Scraper para eBay usando la API oficial de eBay (Browse API).
Requiere registrarse en: https://developer.ebay.com/

Coloca tus credenciales en el archivo .env en la raíz del proyecto:
    EBAY_CLIENT_ID=tu_client_id_aqui
    EBAY_CLIENT_SECRET=tu_client_secret_aqui
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
API_BASE_URL = "https://api.ebay.com/buy/browse/v1"

# Cache del token para no renovarlo en cada llamada
_access_token = None


def _normalizar_external_id(valor) -> str | None:
    """Convierte un identificador crudo del marketplace a string no vacio,
    o None si esta ausente/vacio.

    Usa `is not None` explicitamente (no una comprobacion de veracidad como
    `if valor`) para no tratar 0 -- un id numerico valido -- como ausente,
    y nunca llama a str() sobre un valor None, evitando que se guarde el
    string literal "None"."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _obtener_token_acceso() -> str:
    """
    Obtiene un token de acceso OAuth2 para la API de eBay.
    Usa las credenciales de Client ID y Client Secret.
    """
    global _access_token

    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ eBay: Faltan credenciales. Configura EBAY_CLIENT_ID y EBAY_CLIENT_SECRET en .env")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope/buy.browse",
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        _access_token = data["access_token"]
        print("  🔑 eBay: Token OAuth obtenido correctamente")
        return _access_token
    except Exception as e:
        print(f"❌ eBay: Error obteniendo token: {e}")
        return None


def scraper_ebay(query: str, limite: int = 20) -> list[dict]:
    """
    Busca productos en eBay usando la Browse API oficial.

    Args:
        query: Término de búsqueda (ej: "taladro makita")
        limite: Máximo de resultados (default: 20)

    Returns:
        list[dict]: Lista de productos con formato:
            {
                "titulo": str,
                "precio": float,
                "precio_original": float | None,
                "imagen": str | None,
                "link": str,
                "tienda": "ebay",
                "moneda": str | None,      # price.currency de la Browse API, normalizado
                "disponible": bool | None, # estimatedAvailabilities[].estimatedAvailabilityStatus
                "external_id": str | None, # itemId oficial de la Browse API, como string
            }
    """
    productos = []
    token = _obtener_token_acceso()
    if not token:
        return productos

    url = f"{API_BASE_URL}/item_summary/search"
    params = {
        "q": query,
        "limit": min(limite, 50),
        "filter": "buyingOptions:{FIXED_PRICE}",
    }

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            },
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("itemSummaries", [])

        for item in items:
            try:
                titulo = item.get("title", "")
                link = item.get("itemWebUrl", "")

                # Identificador oficial del item en la Browse API. Se
                # convierte a string no vacio; si no viene o queda vacio
                # tras convertir, se deja en None (no se inventa).
                external_id = _normalizar_external_id(item.get("itemId"))

                # Precio actual
                price_data = item.get("price", {})
                if not price_data:
                    continue
                precio = float(price_data.get("value", 0))
                if precio <= 0:
                    continue

                # Moneda real entregada por la Browse API (price.currency),
                # normalizada. No se inventa una moneda si la respuesta no
                # la trae: se deja en None.
                moneda = price_data.get("currency")
                moneda = moneda.strip().upper() if moneda else None

                # Precio original (si aplica descuento)
                precio_original = None
                if "strikethroughPrice" in item:
                    try:
                        precio_original = float(item["strikethroughPrice"].get("value", 0))
                    except:
                        pass

                # Disponibilidad: solo si la Browse API la informa
                # explicitamente via estimatedAvailabilities[].
                # estimatedAvailabilityStatus (no siempre presente en los
                # resultados de busqueda). Si no viene o el valor no es uno
                # de los reconocidos, se deja en None (nunca se asume True).
                disponible = None
                estimaciones = item.get("estimatedAvailabilities")
                if estimaciones:
                    estado = estimaciones[0].get("estimatedAvailabilityStatus")
                    if estado == "OUT_OF_STOCK":
                        disponible = False
                    elif estado in ("IN_STOCK", "LIMITED_STOCK"):
                        disponible = True

                # Imagen
                imagen = None
                images = item.get("thumbnailImages", [])
                if images:
                    imagen = images[0].get("imageUrl")

                productos.append({
                    "titulo": titulo,
                    "precio": precio,
                    "precio_original": precio_original,
                    "imagen": imagen,
                    "link": link,
                    "tienda": "ebay",
                    "moneda": moneda,
                    "disponible": disponible,
                    "external_id": external_id,
                })

            except Exception:
                continue

        print(f"  📦 eBay: {len(productos)} resultados para '{query}'")

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print(f"❌ eBay: Token expirado o inválido. Verifica tus credenciales en .env")
        elif response.status_code == 403:
            print(f"❌ eBay: Sin permisos. Verifica tus Application Keys en developer.ebay.com")
        else:
            print(f"❌ eBay: Error HTTP {response.status_code}: {e}")
    except Exception as e:
        print(f"❌ eBay: Error en búsqueda '{query}': {e}")

    return productos

