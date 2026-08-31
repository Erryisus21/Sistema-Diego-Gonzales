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
                "tienda": "etsy"
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

                # Precio actual
                price_data = item.get("price", {})
                if not price_data or not price_data.get("amount"):
                    continue
                precio = float(price_data["amount"])
                if precio <= 0:
                    continue

                # Divisor de moneda
                currency = price_data.get("currency_code", "USD")

                # Etsy no suele tener "precio original/tachado" directamente
                # Pero podemos ver si "original_price" existe
                precio_original = None
                if "original_price" in item and item["original_price"]:
                    try:
                        precio_original = float(item["original_price"]["amount"])
                    except:
                        pass

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

