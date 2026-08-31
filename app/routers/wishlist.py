"""
Router de wishlist.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import SessionLocal
from app.models import Producto

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class WishlistAdd(BaseModel):
    url: str
    nombre: str
    imagen_url: str = None
    tienda: str
    categoria: str = None


@router.get("/")
def listar_wishlist(db: Session = Depends(get_db)):
    """Devuelve todos los productos en wishlist."""
    productos = db.query(Producto).filter(Producto.en_wishlist == True).all()
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "url": p.url,
            "imagen_url": p.imagen_url,
            "tienda": p.tienda,
            "categoria": p.categoria,
            "precio_actual": p.precio_actual,
            "precio_original": p.precio_original,
            "precio_al_agregar_wishlist": p.precio_al_agregar_wishlist,
        }
        for p in productos
    ]


@router.post("/")
def agregar_wishlist(data: WishlistAdd, db: Session = Depends(get_db)):
    """Agrega un producto a la wishlist. Guarda el precio al momento de agregar."""
    producto = db.query(Producto).filter(Producto.url == data.url).first()
    if producto:
        # Ya existe - marcarlo como wishlist y guardar precio actual
        producto.en_wishlist = True
        producto.precio_al_agregar_wishlist = producto.precio_actual
        db.commit()
        return {"mensaje": "Producto agregado a wishlist", "id": producto.id}

    # Si no existe, crear uno nuevo (caso raro, pero por si acaso)
    nuevo = Producto(
        nombre=data.nombre,
        url=data.url,
        imagen_url=data.imagen_url,
        tienda=data.tienda,
        categoria=data.categoria,
        precio_actual=0,
        en_wishlist=True,
        precio_al_agregar_wishlist=0,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Producto agregado a wishlist", "id": nuevo.id}


# IMPORTANTE: /por-url debe ir ANTES de /{producto_id}
# porque FastAPI evalúa las rutas en orden y /{producto_id}
# haría match con cualquier cosa (incluido "por-url").
@router.delete("/por-url")
def quitar_wishlist_por_url(
    url: str = Query(..., description="URL del producto a eliminar"),
    db: Session = Depends(get_db),
):
    """Quita un producto de la wishlist por URL (query param)."""
    producto = db.query(Producto).filter(Producto.url == url).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    producto.en_wishlist = False
    producto.precio_al_agregar_wishlist = None
    db.commit()
    return {"mensaje": "Producto removido de wishlist"}


@router.delete("/{producto_id}")
def quitar_wishlist(producto_id: int, db: Session = Depends(get_db)):
    """Quita un producto de la wishlist por ID."""
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    producto.en_wishlist = False
    producto.precio_al_agregar_wishlist = None
    db.commit()
    return {"mensaje": "Producto removido de wishlist"}