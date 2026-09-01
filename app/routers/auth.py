"""
Router de autenticación: registro, login y perfil del usuario actual.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app import schemas
from app.services.seguridad import (
    crear_access_token,
    get_usuario_actual,
    hash_password,
    verificar_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_CREDENCIALES_INVALIDAS_MSG = "Credenciales inválidas"


@router.post("/registro", response_model=schemas.UsuarioResponse, status_code=status.HTTP_201_CREATED)
def registro(data: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    email = data.email.lower()

    existente = db.query(Usuario).filter(Usuario.email == email).first()
    if existente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado")

    usuario = Usuario(
        nombre=data.nombre,
        email=email,
        password_hash=hash_password(data.password),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=schemas.TokenResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = data.email.lower()
    usuario = db.query(Usuario).filter(Usuario.email == email).first()

    password_hash = usuario.password_hash if usuario else None
    password_valido = verificar_password(data.password, password_hash)

    if not usuario or not password_valido or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_CREDENCIALES_INVALIDAS_MSG,
        )

    access_token = crear_access_token(usuario.id)
    return schemas.TokenResponse(access_token=access_token)


@router.get("/me", response_model=schemas.UsuarioResponse)
def me(usuario_actual: Usuario = Depends(get_usuario_actual)):
    return usuario_actual
