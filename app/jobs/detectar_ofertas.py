from urllib.parse import urlparse

from app.productos import PRODUCTOS
from app.scrapers.ebay import scraper_ebay
from app.scrapers.etsy import scraper_etsy
from app.services.precios import obtener_precio_promedio, guardar_precio, VENTANA_OFERTAS_DIAS
from app.database import SessionLocal
from app.models import Producto, Oferta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime

DESCUENTO_MINIMO = 5.0  # % minimo para considerar oferta

# Lista de scrapers disponibles (nombre_mostrar, funcion_scraper)
SCRAPERS = [
    ("eBay", scraper_ebay),
    ("Etsy", scraper_etsy),
]


def _url_valida(url) -> bool:
    """Valida que `url` sea segura para usarse como Producto.url: un string
    no vacio (ni solo espacios en blanco) que represente una URL absoluta
    con esquema http o https, netloc no vacio y un hostname parseable. No
    normaliza ni modifica el valor -- solo determina si es seguro guardarlo
    tal cual llega del marketplace/scraper; una URL relativa, vacia, en
    blanco, con otro esquema (ftp, javascript, mailto, etc.) o con una
    autoridad malformada (p. ej. puerto invalido) se considera invalida.

    `partes.hostname` (a diferencia de `partes.netloc`) ya excluye
    userinfo/puerto y puede lanzar ValueError con una autoridad malformada;
    por eso se accede dentro del mismo try/except que urlparse()."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        partes = urlparse(url)
        host = partes.hostname
    except ValueError:
        return False
    return partes.scheme in ("http", "https") and bool(partes.netloc) and bool(host)


def _actualizar_precio_original_si_valido(producto: Producto, item: dict) -> None:
    """Actualiza Producto.precio_original solo con un valor real entregado
    por el scraper/marketplace (item['precio_original']).

    Nunca se usa aqui el promedio historico ni ningun otro valor calculado
    como referencia interna: ese promedio es exclusivo de la deteccion de
    ofertas y vive en Oferta.precio_promedio. Si esta lectura no trae un
    precio_original valido, se conserva el que ya hubiera (no se inventa
    uno a partir del historial ni se borra el anterior por una lectura
    incompleta)."""
    precio_original_item = item.get("precio_original")
    if precio_original_item:
        producto.precio_original = precio_original_item


def _actualizar_moneda_si_valida(producto: Producto, item: dict) -> None:
    """Actualiza Producto.moneda solo con el valor real que trae esta
    lectura (`item['moneda']`, ya normalizado por el scraper con
    strip().upper()). Si la fuente no informa moneda en esta corrida, se
    conserva la que ya hubiera; nunca se limpia por una lectura incompleta."""
    moneda_item = item.get("moneda")
    if moneda_item:
        producto.moneda = moneda_item


def _actualizar_disponible_si_valido(producto: Producto, item: dict) -> None:
    """Actualiza Producto.disponible solo cuando el item trae un booleano
    explicito (True o False). A diferencia de moneda/precio_original, aqui
    se usa `is not None` porque False es un valor valido y significativo
    (no debe tratarse como "sin dato")."""
    disponible_item = item.get("disponible")
    if disponible_item is not None:
        producto.disponible = disponible_item


def guardar_oferta_db(db: Session, item: dict, precio_promedio: float, descuento: float, categoria: str):
    """Registra el producto/precio y, si corresponde, un nuevo evento de
    Oferta.

    `precio_promedio` es el precio de referencia (historico o tachado)
    usado unicamente para calcular el descuento; se guarda en
    Oferta.precio_promedio y NUNCA se escribe en Producto.precio_original.
    Solo se llama cuando ya se determino que el producto esta disponible
    (o no se sabe con certeza); el llamador (procesar_resultados) filtra
    el caso disponible=False antes de llegar aqui.
    """
    producto = db.query(Producto).filter(Producto.url == item["link"]).first()
    moneda_item = item.get("moneda")
    es_creacion_nueva = producto is None

    if es_creacion_nueva:
        nuevo_producto = Producto(
            nombre=item["titulo"],
            url=item["link"],
            imagen_url=item.get("imagen"),
            tienda=item.get("tienda", "mercadolibre"),
            categoria=categoria,
            precio_actual=item["precio"],
            precio_original=item.get("precio_original"),
            moneda=moneda_item,
            disponible=item.get("disponible"),
            fecha_actualizacion=datetime.utcnow(),
        )
        try:
            # SAVEPOINT (begin_nested, portable entre SQLite y PostgreSQL):
            # si el flush falla, SOLO se deshace esta insercion, sin tocar
            # ningun cambio ya pendiente de otros items en la misma
            # transaccion/sesion -- a diferencia de un db.rollback() a
            # nivel de sesion, que descartaria TODO lo pendiente.
            with db.begin_nested():
                db.add(nuevo_producto)
                db.flush()
        except IntegrityError:
            # Carrera con otro proceso/corrida que ya inserto un Producto
            # con esta misma url (UNIQUE) entre nuestro SELECT y este
            # flush. Se descarta nuestro intento (sin duplicar) y se
            # continua con el que ya existe, igual que si hubieramos
            # entrado por la rama de "producto existente" desde el inicio.
            producto = db.query(Producto).filter(Producto.url == item["link"]).first()
            if not producto:
                # Defensivo: el conflicto no dejo un producto localizable.
                # Se omite este item sin abortar el resto de la corrida.
                return
            es_creacion_nueva = False
        else:
            producto = nuevo_producto

    if es_creacion_nueva:
        precio_anterior = None
    else:
        # Capturar el precio real inmediatamente anterior ANTES de
        # sobreescribirlo: es la base para decidir si este es un evento de
        # oferta nuevo o la continuacion de uno que ya veniamos observando.
        precio_anterior = producto.precio_actual
        producto.precio_actual = item["precio"]
        _actualizar_precio_original_si_valido(producto, item)
        _actualizar_moneda_si_valida(producto, item)
        _actualizar_disponible_si_valido(producto, item)
        producto.fecha_actualizacion = datetime.utcnow()

    # Se usa la moneda ENTRANTE de este resultado (moneda_item), no
    # producto.moneda: si la fuente cambia de moneda entre corridas, el
    # historial nuevo debe registrarse bajo la moneda actual y no bajo una
    # moneda vieja que ya no corresponde a este precio.
    guardar_precio(db, producto.id, item["precio"], moneda=moneda_item)

    # Nuevo evento de Oferta solo si el precio REAL anterior del producto
    # (capturado arriba, antes de sobreescribirlo) difiere del precio
    # actual detectado -- tolerancia de centavos via round(...,2), mismo
    # criterio que guardar_precio(). No se compara contra la ultima fila
    # de Oferta: un ciclo baja->sube->misma baja debe generar una segunda
    # fila aunque el precio coincida con una oferta historica, porque
    # representa un evento nuevo (el producto estuvo, entremedio, a un
    # precio distinto).
    es_evento_nuevo = (
        precio_anterior is None or round(precio_anterior, 2) != round(item["precio"], 2)
    )

    if es_evento_nuevo:
        oferta = Oferta(
            producto_id=producto.id,
            precio_actual=item["precio"],
            precio_promedio=precio_promedio,
            descuento=descuento,
        )
        db.add(oferta)

    db.commit()


def guardar_precio_nuevo(db: Session, item: dict, categoria: str):
    """Registra un producto nuevo con su primer precio historico.

    Producto.precio_original, moneda y disponible solo se llenan si el
    scraper entrego un valor real en el item; si no, quedan en None (no se
    inventan)."""
    moneda_item = item.get("moneda")
    nuevo_producto = Producto(
        nombre=item["titulo"],
        url=item["link"],
        imagen_url=item.get("imagen"),
        tienda=item.get("tienda", "mercadolibre"),
        categoria=categoria,
        precio_actual=item["precio"],
        precio_original=item.get("precio_original"),
        moneda=moneda_item,
        disponible=item.get("disponible"),
        fecha_actualizacion=datetime.utcnow(),
    )
    try:
        # SAVEPOINT (begin_nested): el rollback ante conflicto queda
        # acotado a esta insercion, sin descartar cambios pendientes de
        # otros items en la misma transaccion/sesion.
        with db.begin_nested():
            db.add(nuevo_producto)
            db.flush()
    except IntegrityError:
        # Carrera: ya existe un Producto con esta misma url (por ejemplo,
        # otra corrida del job lo creo entre nuestro chequeo y este
        # flush). Se descarta este intento y se reutiliza el existente en
        # vez de abortar el procesamiento del resto de items.
        producto = db.query(Producto).filter(Producto.url == item["link"]).first()
        if not producto:
            return
    else:
        producto = nuevo_producto
    guardar_precio(db, producto.id, item["precio"], moneda=moneda_item)
    db.commit()


def procesar_resultados(db: Session, resultados: list, categoria: str):
    """Procesa los resultados de cualquier scraper y detecta ofertas."""
    for item in resultados:
        link = item.get("link")
        if not _url_valida(link):
            # URL ausente, vacia, en blanco, relativa o con esquema no
            # http/https: no es segura para usarse como Producto.url. Se
            # omite este item por completo (no se busca ni se crea
            # Producto, HistorialPrecio ni Oferta) sin abortar el resto de
            # la corrida.
            titulo = item.get("titulo", "?")
            print(f"  Producto: {str(titulo)[:50]}")
            print(f"  URL invalida u omitida ({link!r}): se descarta el item\n")
            continue

        precio = item.get("precio", 0)
        precio_original_item = item.get("precio_original")
        moneda_item = item.get("moneda")
        disponible_item = item.get("disponible")

        if precio <= 0:
            continue

        producto_db = db.query(Producto).filter(Producto.url == item["link"]).first()

        if disponible_item is False:
            # Explicitamente no disponible: no puede estar en oferta. Se
            # actualiza el estado (disponible/moneda/fecha_actualizacion)
            # del producto pero no se calcula descuento ni se toca su
            # historial de precios (ese precio ya no es uno real de compra).
            if not producto_db:
                nuevo_producto = Producto(
                    nombre=item["titulo"],
                    url=item["link"],
                    imagen_url=item.get("imagen"),
                    tienda=item.get("tienda", "mercadolibre"),
                    categoria=categoria,
                    precio_actual=precio,
                    precio_original=item.get("precio_original"),
                    moneda=moneda_item,
                    disponible=False,
                    fecha_actualizacion=datetime.utcnow(),
                )
                try:
                    # SAVEPOINT (begin_nested): acota el rollback a esta
                    # insercion, sin descartar cambios pendientes de otros
                    # items en la misma transaccion/sesion.
                    with db.begin_nested():
                        db.add(nuevo_producto)
                        db.flush()
                except IntegrityError:
                    # Carrera: ya existe un Producto con esta misma url.
                    # Se descarta este intento y se actualiza el existente
                    # en vez de abortar el resto de la corrida.
                    producto_db = db.query(Producto).filter(Producto.url == item["link"]).first()
                    if not producto_db:
                        continue
                    _actualizar_moneda_si_valida(producto_db, item)
                    producto_db.disponible = False
                    producto_db.fecha_actualizacion = datetime.utcnow()
                else:
                    producto_db = nuevo_producto
            else:
                _actualizar_moneda_si_valida(producto_db, item)
                producto_db.disponible = False
                producto_db.fecha_actualizacion = datetime.utcnow()
            db.commit()
            print(f"  Producto: {item['titulo'][:50]}")
            print(f"  No disponible: se omite deteccion de oferta\n")
            continue

        # Prioridad 1: promedio historico real (cuando haya varias lecturas).
        # Se consulta con la moneda ENTRANTE de este resultado (moneda_item),
        # no con producto_db.moneda: si la fuente cambia de moneda entre
        # corridas, comparar contra un historial guardado bajo la moneda
        # vieja mezclaria precios incompatibles. Misma ventana
        # (VENTANA_OFERTAS_DIAS) que usan las estadisticas de producto en
        # GET /producto/{id}, para que el descuento detectado aqui sea
        # consistente con lo que ve el usuario en el detalle.
        promedio_historico = None
        if producto_db:
            promedio_historico = obtener_precio_promedio(
                db, producto_db.id, dias=VENTANA_OFERTAS_DIAS, moneda=moneda_item
            )

        # Decidir que usar como "precio de referencia"
        if promedio_historico and promedio_historico > precio:
            # Usar historico real
            promedio = promedio_historico
            fuente = "historico"
        elif precio_original_item and precio_original_item > precio:
            # Usar precio original/tachado del producto. No se registra el
            # producto todavia aqui: si el descuento supera el umbral,
            # guardar_oferta_db() lo creara directamente, y su
            # deduplicacion necesita ver un producto realmente nuevo
            # (precio_anterior=None) para no perderse la primera oferta
            # por culpa de un pre-registro redundante con el mismo precio.
            promedio = precio_original_item
            fuente = f"{item['tienda']}-tachado"
        else:
            # Fallback: sin oferta detectable, solo registrar precio
            if not producto_db:
                guardar_precio_nuevo(db, item, categoria)
            else:
                guardar_precio(db, producto_db.id, precio, moneda=moneda_item)
                # Actualizar precio actual del producto aunque no sea oferta
                producto_db.precio_actual = precio
                _actualizar_precio_original_si_valido(producto_db, item)
                _actualizar_moneda_si_valida(producto_db, item)
                _actualizar_disponible_si_valido(producto_db, item)
                producto_db.fecha_actualizacion = datetime.utcnow()
                db.commit()
            print(f"  Producto: {item['titulo'][:50]}")
            print(f"  Precio: ${precio:,.2f} (sin precio de referencia, no es oferta)\n")
            continue

        descuento = ((promedio - precio) / promedio) * 100

        print(f"  Producto: {item['titulo'][:50]}")
        print(f"  Precio: ${precio:,.2f} | Antes: ${promedio:,.2f} | Descuento: {descuento:.1f}% ({fuente}) | Tienda: {item['tienda']}")

        if descuento >= DESCUENTO_MINIMO:
            print(f"  OFERTA DETECTADA\n")
            guardar_oferta_db(db, item, promedio, descuento, categoria)
        else:
            if producto_db:
                guardar_precio(db, producto_db.id, precio, moneda=moneda_item)
                producto_db.precio_actual = precio
                _actualizar_precio_original_si_valido(producto_db, item)
                _actualizar_moneda_si_valida(producto_db, item)
                _actualizar_disponible_si_valido(producto_db, item)
                producto_db.fecha_actualizacion = datetime.utcnow()
                db.commit()
            else:
                # Tachado real pero con descuento por debajo del umbral y
                # producto todavia inexistente: registrar el precio inicial
                # igual que en el caso sin ninguna referencia.
                guardar_precio_nuevo(db, item, categoria)
            print()


def detectar_ofertas():
    """Funcion principal que se llama desde el scheduler."""
    ejecutar()


def ejecutar():
    db = SessionLocal()

    try:
        for producto_cfg in PRODUCTOS:
            nombre = producto_cfg["nombre"]
            categoria = producto_cfg.get("categoria", "general")
            print(f"\n{'='*60}")
            print(f"Buscando: {nombre.upper()} en todas las tiendas")
            print(f"{'='*60}")

            for nombre_tienda, scraper in SCRAPERS:
                print(f"\n  [{nombre_tienda}] Buscando '{nombre}'...")
                try:
                    resultados = scraper(nombre)
                except Exception as e:
                    print(f"  [{nombre_tienda}] Error al buscar {nombre}: {e}")
                    continue

                if not resultados:
                    print(f"  [{nombre_tienda}] Sin resultados")
                    continue

                print(f"  [{nombre_tienda}] {len(resultados)} resultado(s)")
                procesar_resultados(db, resultados, categoria)

    finally:
        db.close()


if __name__ == "__main__":
    ejecutar()
