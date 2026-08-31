import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

SELECTORES_PRECIO = [
    "span.a-offscreen",                  # precio estándar
    "span.a-price > span.a-offscreen",   # variante
    "#priceblock_ourprice",              # legacy
    "#priceblock_dealprice",             # ofertas
]

def limpiar_precio(texto: str):
    try:
        return float(
            texto.replace("$", "")
                 .replace(",", "")
                 .replace("MXN", "")
                 .strip()
        )
    except:
        return None

def obtener_precio_amazon(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    for selector in SELECTORES_PRECIO:
        elemento = soup.select_one(selector)
        if elemento and elemento.text:
            precio = limpiar_precio(elemento.text)
            if precio and precio > 0:
                return precio

    return None