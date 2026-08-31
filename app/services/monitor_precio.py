import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
}

def limpiar_precio(texto: str):
    try:
        return float(
            texto.replace("$", "")
                 .replace(".", "")
                 .replace(",", "")
                 .strip()
        )
    except:
        return None

def obtener_precio_mercadolibre(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # 1️⃣ Precio principal (más común)
    precio = soup.select_one("span.andes-money-amount__fraction")
    if precio:
        valor = limpiar_precio(precio.text)
        if valor:
            return valor

    # 2️⃣ Precio legacy
    precio = soup.select_one("span.price-tag-fraction")
    if precio:
        valor = limpiar_precio(precio.text)
        if valor:
            return valor

    # 3️⃣ Meta tag (muy confiable)
    meta = soup.find("meta", property="product:price:amount")
    if meta and meta.get("content"):
        try:
            return float(meta["content"])
        except:
            pass

    return None