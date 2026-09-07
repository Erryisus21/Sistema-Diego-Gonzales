"""
Scraper para Etsy usando la API oficial de Etsy v3.
Requiere registrarse en: https://developers.etsy.com/

Coloca tus credenciales en el archivo .env en la raíz del proyecto:
    ETSY_API_KEY=tu_api_key_aqui
    ETSY_API_SECRET=tu_api_secret_aqui
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ETSY_API_KEY")
API_SECRET = os.getenv("ETSY_API_SECRET")
API_BASE_URL = "https://openapi.etsy.com/v3"


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


def scraper_etsy(query: str, limite: int = 20) -> list[dict]:
    """
    Busca productos en Etsy usando la API oficial v3.

    Args:
        query: Término de búsqueda (ej: "mochila artesanal")
        limite: Máximo de resultados (default: 20)

    Returns:
        list[dict]: Lista de productos con formato:
            {
                "titulo": str,
                "precio": float,
                "precio_original": float | None,
                "imagen": str | None,
                "link": str,
                "tienda": "etsy",
                "moneda": str | None,      # price.currency_code de la API v3, normalizado
                "disponible": bool | None, # quantity > 0 del listing
                "external_id": str | None, # listing_id oficial de la API v3, como string
            }
    """
    productos = []

    if not API_KEY:
        print("❌ Etsy: Falta API Key. Configura ETSY_API_KEY en .env")
        return productos

    url = f"{API_BASE_URL}/application/listings/active"
    params = {
        "keywords": query,
        "limit": min(limite, 100),
        "sort_on": "relevance",
        "includes": "Images",
    }

    headers = {
        "x-api-key": API_KEY,
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("results", [])

        for item in items:
            try:
                titulo = item.get("title", "")
                listing_id = item.get("listing_id", "")

                # Identificador oficial del listing en la API v3 (se toma
                # del valor crudo, no de `listing_id` con su default ""
                # usado abajo para construir el link).
                external_id = _normalizar_external_id(item.get("listing_id"))

                # Precio actual
                price_data = item.get("price", {})
                if not price_data or not price_data.get("amount"):
                    continue
                precio = float(price_data["amount"])
                if precio <= 0:
                    continue

                # Moneda real entregada por la API v3 (price.currency_code),
                # normalizada. No se inventa una moneda (ni se asume USD)
                # si la respuesta no la trae: se deja en None.
                currency = price_data.get("currency_code")
                moneda = currency.strip().upper() if currency else None

                # Etsy no suele tener "precio original/tachado" directamente
                # Pero podemos ver si "original_price" existe
                precio_original = None
                if "original_price" in item and item["original_price"]:
                    try:
                        precio_original = float(item["original_price"]["amount"])
                    except:
                        pass

                # Disponibilidad: Etsy informa la cantidad disponible en
                # 'quantity' para los listados devueltos (activos). Si el
                # campo no viene o no es un entero, se deja en None (nunca
                # se asume True).
                disponible = None
                cantidad = item.get("quantity")
                if isinstance(cantidad, int):
                    disponible = cantidad > 0

                # URL del producto
                shop_name = item.get("shop", {}).get("shop_name", "shop")
                link = f"https://www.etsy.com/listing/{listing_id}"

                # Imagen principal
                imagen = None
                images = item.get("Images", [])
                if images:
                    image_data = images[0]
                    # Preferir la imagen de mayor resolución
                    for size in ["url_fullxfull", "url_570xN", "url_340x270", "url_75x75"]:
                        if image_data.get(size):
                            imagen = image_data[size]
                            break

                productos.append({
                    "titulo": titulo,
                    "precio": precio,
                    "precio_original": precio_original,
                    "imagen": imagen,
                    "link": link,
                    "tienda": "etsy",
                    "moneda": moneda,
                    "disponible": disponible,
                    "external_id": external_id,
                })

            except Exception:
                continue

        print(f"  📦 Etsy: {len(productos)} resultados para '{query}'")

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print(f"❌ Etsy: API Key inválida. Verifica ETSY_API_KEY en .env")
        elif response.status_code == 403:
            print(f"❌ Etsy: Sin permisos. Verifica tu API Key en developrs.etsy.com")
        elif response.status_code == 429:
            print(f"❌ Etsy: Límite de requests excedido. Espera un momento.")
        else:
            print(f"❌ Etsy: Error HTTP {response.status_code}: {e}")
    except Exception as e:
        print(f"❌ Etsy: Error en búsqueda '{query}': {e}")

    return productos

