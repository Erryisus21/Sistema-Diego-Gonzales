"""
Router para registro de tokens de dispositivos.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import SessionLocal
from app.models import PushToken

router = APIRouter(prefix="/push", tags=["push"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TokenRequest(BaseModel):
    token: str
    plataforma: str = "ios"


@router.post("/registrar")
def registrar_token(data: TokenRequest, db: Session = Depends(get_db)):
    """Registra un token de dispositivo o lo reactiva si ya existía."""
    existente = db.query(PushToken).filter(PushToken.token == data.token).first()

    if existente:
        existente.activo = True
        existente.plataforma = data.plataforma
        db.commit()
        return {"mensaje": "Token actualizado", "id": existente.id}

    nuevo = PushToken(token=data.token, plataforma=data.plataforma, activo=True)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Token registrado", "id": nuevo.id}


@router.get("/tokens")
def listar_tokens(db: Session = Depends(get_db)):
    """Lista todos los tokens activos (para debug)."""
    tokens = db.query(PushToken).filter(PushToken.activo == True).all()
    return [{"id": t.id, "token": t.token[:30] + "...", "plataforma": t.plataforma} for t in tokens]