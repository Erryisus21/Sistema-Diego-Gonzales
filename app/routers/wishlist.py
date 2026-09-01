"""
Router de wishlist, por usuario autenticado.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models import Producto, Usuario, WishlistItem
from app import schemas
from app.services.seguridad import get_usuario_actual

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


class WishlistAdd(BaseModel):
    url: str
    nombre: str
    imagen_url: str = None
    tienda: str
    categoria: str = None
    precio_actual: float = Field(gt=0)


@router.get("/", response_model=list[schemas.WishlistItemResponse])
def listar_wishlist(
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Devuelve la wishlist del usuario autenticado."""
    items = db.query(WishlistItem).filter(WishlistItem.usuario_id == usuario_actual.id).all()
    return [
        {
            "id": item.id,
            "producto_id": item.producto.id,
            "nombre": item.producto.nombre,
            "url": item.producto.url,
            "imagen_url": item.producto.imagen_url,
            "tienda": item.producto.tienda,
            "categoria": item.producto.categoria,
            "precio_actual": item.producto.precio_actual,
            "precio_original": item.producto.precio_original,
            "precio_al_agregar": item.precio_al_agregar,
            "fecha_agregado": item.fecha_agregado,
        }
        for item in items
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
def agregar_wishlist(
    data: WishlistAdd,
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Agrega un producto a la wishlist del usuario autenticado, guardando
    el precio que el usuario vio al momento de agregar (precio_al_agregar
    siempre viene de data.precio_actual, nunca del Producto)."""
    producto = db.query(Producto).filter(Producto.url == data.url).first()
    if not producto:
        producto = Producto(
            nombre=data.nombre,
            url=data.url,
            imagen_url=data.imagen_url,
            tienda=data.tienda,
            categoria=data.categoria,
            precio_actual=data.precio_actual,
        )
        db.add(producto)
        try:
            db.flush()  # asigna producto.id sin cerrar la transacción todavía
        except IntegrityError:
            # Otro request creó el mismo Producto (misma url) en paralelo:
            # descartamos nuestro intento y reutilizamos el que ya existe,
            # sin sobrescribir su precio_actual con el dato del cliente.
            db.rollback()
            producto = db.query(Producto).filter(Producto.url == data.url).first()
            if not producto:
                # Caso defensivo: el flush falló por conflicto pero no
                # encontramos el producto en conflicto. No continuar hacia
                # producto.id con un valor inválido.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se pudo registrar el producto",
                )

    existente = db.query(WishlistItem).filter(
        WishlistItem.usuario_id == usuario_actual.id,
        WishlistItem.producto_id == producto.id,
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El producto ya está en tu wishlist",
        )

    item = WishlistItem(
        usuario_id=usuario_actual.id,
        producto_id=producto.id,
        precio_al_agregar=data.precio_actual,
    )
    db.add(item)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El producto ya está en tu wishlist",
        )

    db.refresh(item)
    return {"mensaje": "Producto agregado a wishlist", "id": item.id, "producto_id": producto.id}


@router.delete("/{producto_id}")
def quitar_wishlist(
    producto_id: int,
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Quita un producto de la wishlist del usuario autenticado.
    Elimina únicamente el WishlistItem, nunca el Producto."""
    item = db.query(WishlistItem).filter(
        WishlistItem.usuario_id == usuario_actual.id,
        WishlistItem.producto_id == producto_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Producto no encontrado en tu wishlist")

    db.delete(item)
    db.commit()
    return {"mensaje": "Producto removido de wishlist"}
