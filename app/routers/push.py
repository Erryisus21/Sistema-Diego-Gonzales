"""
Router para registro de tokens de dispositivos.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import PushToken, Usuario
from app.services.seguridad import get_usuario_actual

router = APIRouter(prefix="/push", tags=["push"])


class TokenRequest(BaseModel):
    token: str
    plataforma: str = "ios"


@router.post("/registrar")
def registrar_token(
    data: TokenRequest,
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Registra un token de dispositivo para el usuario autenticado, o lo
    reactiva si ya existía (siempre que le pertenezca o esté sin dueño)."""
    existente = db.query(PushToken).filter(PushToken.token == data.token).first()

    if existente:
        if existente.usuario_id not in (None, usuario_actual.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este token pertenece a otro usuario",
            )
        existente.usuario_id = usuario_actual.id
        existente.activo = True
        existente.plataforma = data.plataforma
        db.commit()
        return {"mensaje": "Token actualizado", "id": existente.id}

    nuevo = PushToken(
        token=data.token,
        plataforma=data.plataforma,
        activo=True,
        usuario_id=usuario_actual.id,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Token registrado", "id": nuevo.id}


@router.get("/tokens")
def listar_tokens(
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Lista los tokens activos del usuario autenticado (para debug)."""
    tokens = db.query(PushToken).filter(
        PushToken.activo == True,
        PushToken.usuario_id == usuario_actual.id,
    ).all()
    return [{"id": t.id, "token": t.token[:30] + "...", "plataforma": t.plataforma} for t in tokens]
