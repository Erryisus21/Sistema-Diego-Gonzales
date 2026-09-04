"""
Servicio de seguridad: hashing de contraseñas (Argon2 vía pwdlib) y
tokens JWT (PyJWT) para la autenticación de SAVVR.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PasswordResetToken, RefreshToken, Usuario

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


def crear_access_token(usuario_id: int, token_version: int) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "ver": token_version,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])


# --- Refresh tokens ---
REFRESH_TOKEN_BYTES = 64
REFRESH_TOKEN_EXPIRE_DIAS = 30


def generar_refresh_token() -> str:
    """Genera un refresh token opaco criptográficamente seguro.

    El valor devuelto existe en texto plano únicamente en este momento y en
    la respuesta al cliente: nunca se guarda así en la base de datos (solo
    su SHA-256, ver hash_refresh_token) ni debe imprimirse en logs.
    """
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(refresh_token: str) -> str:
    """SHA-256 (hex) del refresh token. Es lo único que se persiste en
    RefreshToken.token_hash — el valor plano nunca llega a la base."""
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def crear_sesion_refresh(db: Session, usuario_id: int) -> str:
    """Crea una nueva sesión RefreshToken (expira en REFRESH_TOKEN_EXPIRE_DIAS
    días) y la agrega a la sesión de BD con db.add() — no hace commit(), el
    llamador conserva el manejo transaccional.

    Devuelve el refresh token en texto plano para entregarlo al cliente;
    es la única vez que existe así, no debe guardarse en ningún otro lado.
    """
    refresh_token = generar_refresh_token()
    sesion = RefreshToken(
        usuario_id=usuario_id,
        token_hash=hash_refresh_token(refresh_token),
        fecha_expiracion=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DIAS),
    )
    db.add(sesion)
    return refresh_token


def buscar_sesion_por_refresh_token(db: Session, refresh_token: str) -> RefreshToken | None:
    """Localiza la sesión RefreshToken correspondiente al valor plano
    recibido, comparando por su hash. No valida vigencia ni estado — el
    llamador decide qué hacer con lo que encuentre (o no encuentre)."""
    token_hash = hash_refresh_token(refresh_token)
    return db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()


# --- Tokens de recuperación de contraseña ---
RESET_TOKEN_BYTES = 64
RESET_TOKEN_EXPIRE_MINUTOS = 30


def generar_token_reset() -> str:
    """Genera un token de recuperación de contraseña opaco y de alta
    entropía.

    El valor devuelto existe en texto plano únicamente en este momento;
    nunca se guarda así en la base de datos (solo su SHA-256, ver
    hash_token_reset) ni debe imprimirse/registrarse en logs.
    """
    return secrets.token_urlsafe(RESET_TOKEN_BYTES)


def hash_token_reset(token: str) -> str:
    """SHA-256 (hex) del token de recuperación. Es lo único que se
    persiste en PasswordResetToken.token_hash — el valor plano nunca
    llega a la base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear_sesion_reset(db: Session, usuario_id: int) -> str:
    """Crea un PasswordResetToken (expira en RESET_TOKEN_EXPIRE_MINUTOS
    minutos) y lo agrega a la sesión de BD con db.add() — no hace
    commit(), el llamador conserva el manejo transaccional.

    Devuelve el token en texto plano para que el llamador se lo entregue
    al mecanismo de envío de correo; no debe guardarse ni registrarse en
    ningún otro lado.
    """
    token = generar_token_reset()
    sesion = PasswordResetToken(
        usuario_id=usuario_id,
        token_hash=hash_token_reset(token),
        fecha_expiracion=datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTOS),
    )
    db.add(sesion)
    return token


def enviar_email_recuperacion(email: str, token: str) -> None:
    """Punto de integración futuro con un proveedor de email real
    (SendGrid, SES, SMTP, etc.). Todavía no hay ningún proveedor
    configurado en SAVVR, así que esta función intencionalmente no hace
    nada por ahora.

    No debe imprimir, registrar (logs) ni persistir `token` en ningún
    lado. Cuando se conecte un proveedor real, esta debería ser la única
    función que haga falta completar, sin tocar la lógica de seguridad
    de generación/hash/consumo del token de recuperación.
    """
    pass


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

    if payload.get("ver") != usuario.token_version:
        # No se distingue este caso de cualquier otro token inválido: el
        # mismo 401 genérico, sin revelar que la versión no coincidió.
        raise _CREDENCIALES_INVALIDAS

    return usuario
