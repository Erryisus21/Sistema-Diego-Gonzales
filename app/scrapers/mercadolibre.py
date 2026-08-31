import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
}

def scraper_mercadolibre(query: str, limite: int = 20) -> list[dict]:
    productos = []
    url = f"https://listado.mercadolibre.com.mx/{query.replace(' ', '-')}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("li.ui-search-layout__item")[:limite]

        for item in items:
            try:
                titulo_el = item.select_one("a.poly-component__title")
                if not titulo_el:
                    continue
                titulo = titulo_el.get_text(strip=True)
                link = titulo_el.get("href", "")

                # Precio actual: dentro de div.poly-price__current
                precio_actual_el = item.select_one("div.poly-price__current span.andes-money-amount__fraction")
                if not precio_actual_el:
                    continue
                precio_actual = float(precio_actual_el.get_text(strip=True).replace(".", "").replace(",", ""))

                # Precio original: dentro de <s> (precio tachado)
                precio_original = None
                precio_tachado = item.select_one("s.andes-money-amount--previous span.andes-money-amount__fraction")
                if precio_tachado:
                    try:
                        precio_original = float(precio_tachado.get_text(strip=True).replace(".", "").replace(",", ""))
                    except:
                        pass

                imagen_el = item.select_one("img.poly-component__picture")
                imagen = None
                if imagen_el:
                    imagen = imagen_el.get("src") or imagen_el.get("data-src")

                productos.append({
                    "titulo": titulo,
                    "precio": precio_actual,
                    "precio_original": precio_original,
                    "imagen": imagen,
                    "link": link,
                    "tienda": "mercadolibre",
                })
            except:
                continue

    except requests.RequestException as e:
        print(f"❌ Error scraping ML para '{query}': {e}")

    return productos