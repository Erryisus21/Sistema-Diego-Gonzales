"""
Servicio de seguridad: hashing de contraseñas (Argon2 vía pwdlib) y
tokens JWT (PyJWT) para la autenticación de SAVVR.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario

# Carga explícita de .env en este módulo: no depender de que otro módulo
# (p. ej. un scraper) haya ejecutado load_dotenv() antes de importar este.
load_dotenv()

# --- Hashing de contraseñas (Argon2 recomendado por pwdlib) ---
password_hasher = PasswordHash.recommended()

# Hash fijo de una contraseña ficticia, calculado una sola vez al importar
# el módulo. Se usa para verificar igual cuando el usuario no existe, y así
# no revelar por diferencia de tiempo si un email está registrado o no.
_HASH_FICTICIO = password_hasher.hash("hash-ficticio-para-mitigar-timing-attacks")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verificar_password(password: str, password_hash: str | None) -> bool:
    """Verifica el password contra el hash. Si password_hash es None
    (usuario inexistente), igual ejecuta una verificación contra un hash
    ficticio para mantener un tiempo de respuesta similar."""
    if password_hash is None:
        password_hasher.verify(password, _HASH_FICTICIO)
        return False
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


# --- JWT ---
# La clave se toma exclusivamente de la variable de entorno: si falta, la
# aplicación debe fallar al arrancar en vez de correr con un secreto débil.
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

# Algoritmo fijado explícitamente en el servidor (nunca leído del token ni del entorno).
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60


def crear_access_token(usuario_id: int) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])


# --- Dependencia para endpoints protegidos (esquema Bearer, no OAuth2 Password Form) ---
bearer_scheme = HTTPBearer()

_CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        payload = decodificar_token(credenciales.credentials)
    except jwt.PyJWTError:
        raise _CREDENCIALES_INVALIDAS

    usuario_id = payload.get("sub")
    if usuario_id is None:
        raise _CREDENCIALES_INVALIDAS

    usuario = db.query(Usuario).filter(Usuario.id == int(usuario_id)).first()
    if not usuario or not usuario.activo:
        raise _CREDENCIALES_INVALIDAS

    return usuario
