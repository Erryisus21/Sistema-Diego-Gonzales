from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Producto

router = APIRouter(prefix="/categorias", tags=["categorias"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


CATEGORIAS = [
    {"id": "herramientas", "nombre": "Herramientas", "icono": "🔧"},
    {"id": "electronica", "nombre": "Electrónica", "icono": "📱"},
    {"id": "hogar", "nombre": "Hogar", "icono": "🏠"},
    {"id": "moda", "nombre": "Moda", "icono": "👕"},
    {"id": "deportes", "nombre": "Deportes", "icono": "⚽"},
]


@router.get("/")
def listar_categorias(db: Session = Depends(get_db)):
    resultado = []
    for cat in CATEGORIAS:
        total = db.query(Producto).filter(
            Producto.categoria == cat["id"]
        ).count()
        resultado.append({**cat, "total_productos": total})
    return resultado