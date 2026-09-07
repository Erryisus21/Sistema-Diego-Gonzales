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
    """Conteo del CATÁLOGO COMPLETO (Producto) por categoría, sin filtrar
    por vigencia ni disponibilidad -- es intencional que `total_productos`
    aquí no coincida con lo que GET /ofertas?categoria=X devuelve: este
    endpoint cuenta todo lo que SAVVR conoce de esa categoría (haya tenido
    oferta o no, esté disponible o no), igual que GET /busqueda ahora
    busca sobre ese mismo catálogo completo. /ofertas es un universo
    distinto y más chico (solo ofertas vigentes); no se debe intentar que
    ambos números coincidan."""
    resultado = []
    for cat in CATEGORIAS:
        total = db.query(Producto).filter(
            Producto.categoria == cat["id"]
        ).count()
        resultado.append({**cat, "total_productos": total})
    return resultado