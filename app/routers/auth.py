"""
Router de autenticación: registro, login, refresh, logout y perfil del
usuario actual.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PasswordResetToken, PushToken, RefreshToken, Usuario
from app import schemas
from app.services.seguridad import (
    buscar_sesion_por_refresh_token,
    crear_access_token,
    crear_sesion_refresh,
    crear_sesion_reset,
    enviar_email_recuperacion,
    get_usuario_actual,
    hash_password,
    hash_refresh_token,
    hash_token_reset,
    verificar_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_CREDENCIALES_INVALIDAS_MSG = "Credenciales inválidas"
_RESET_INVALIDO_MSG = "El enlace de recuperación no es válido o ya expiró."


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

    access_token = crear_access_token(usuario.id, usuario.token_version)
    refresh_token = crear_sesion_refresh(db, usuario.id)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return schemas.TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(data: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """Renueva la sesión rotando el refresh token de forma segura ante
    solicitudes concurrentes: la revocación de R1 es un UPDATE condicional
    atómico (no un SELECT seguido de una mutación en Python), así que solo
    una solicitud puede consumir un mismo refresh token. El anterior nunca
    vuelve a funcionar después de una rotación exitosa."""
    token_hash = hash_refresh_token(data.refresh_token)
    ahora = datetime.utcnow()

    # Revocación atómica: si otra solicitud ya consumió este token, o si
    # nunca fue válido o ya expiró, esto afecta 0 filas — sin ventana entre
    # "verificar" y "actuar".
    resultado = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revocado == False,
            RefreshToken.fecha_expiracion > ahora,
        )
        .values(revocado=True, fecha_revocacion=ahora)
    )

    if resultado.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_CREDENCIALES_INVALIDAS_MSG,
        )

    # Ya "ganamos" la carrera sobre este token; ahora sí es seguro leer el
    # resto de datos que necesitamos (dentro de la misma transacción).
    sesion = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    usuario = sesion.usuario

    if usuario is None or not usuario.activo:
        # Mismo comportamiento externo que antes: si el usuario está
        # inactivo, se rechaza y no se consume el token (el rollback
        # deshace la revocación pendiente, R1 sigue utilizable).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_CREDENCIALES_INVALIDAS_MSG,
        )

    # Rotación transaccional: la revocación de R1 (ya ejecutada arriba) y
    # la creación de R2 se confirman en el mismo commit, para que un fallo
    # no deje el anterior revocado sin que exista el nuevo.
    nuevo_refresh_token = crear_sesion_refresh(db, sesion.usuario_id)
    nuevo_access_token = crear_access_token(sesion.usuario_id, usuario.token_version)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return schemas.TokenResponse(access_token=nuevo_access_token, refresh_token=nuevo_refresh_token)


@router.post("/logout", response_model=schemas.LogoutResponse)
def logout(data: schemas.LogoutRequest, db: Session = Depends(get_db)):
    """Revoca únicamente la sesión correspondiente al refresh token
    recibido, si existe y no estaba ya revocada. Respuesta genérica en
    todos los casos para no filtrar si el token era válido o existía.
    No invalida el access token ya emitido (sigue vigente hasta su
    expiración de 60 minutos) ni cierra otras sesiones del usuario."""
    sesion = buscar_sesion_por_refresh_token(db, data.refresh_token)

    if sesion is not None and not sesion.revocado:
        sesion.revocado = True
        sesion.fecha_revocacion = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return schemas.LogoutResponse(mensaje="Sesión cerrada")


@router.post("/desactivar-cuenta", response_model=schemas.LogoutResponse)
def desactivar_cuenta(
    data: schemas.DesactivarCuentaRequest,
    usuario_actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Desactivación lógica de cuenta (requiere confirmar la contraseña
    actual). No borra al usuario ni ninguno de sus datos — solo cambia
    estados (Usuario.activo, RefreshToken.revocado, PushToken.activo) en
    una sola transacción: Usuario.activo=False, se revocan todos los
    RefreshToken activos y se desactivan todos los PushToken activos."""
    if not verificar_password(data.password, usuario_actual.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_CREDENCIALES_INVALIDAS_MSG,
        )

    ahora = datetime.utcnow()

    usuario_actual.activo = False

    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.usuario_id == usuario_actual.id,
            RefreshToken.revocado == False,
        )
        .values(revocado=True, fecha_revocacion=ahora)
    )

    db.execute(
        update(PushToken)
        .where(
            PushToken.usuario_id == usuario_actual.id,
            PushToken.activo == True,
        )
        .values(activo=False)
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return schemas.LogoutResponse(mensaje="Cuenta desactivada")


@router.post("/recuperar", response_model=schemas.LogoutResponse)
def recuperar(data: schemas.RecuperarPasswordRequest, db: Session = Depends(get_db)):
    """Inicia la recuperación de contraseña. Responde exactamente el mismo
    mensaje exista o no la cuenta (y exista o no esté activa, y falle o
    no el envío del correo), para no revelar nada sobre el email recibido.
    Solo si el usuario existe y está activo: se invalidan sus enlaces de
    recuperación anteriores sin usar (solo el más reciente puede
    utilizarse) y se crea un PasswordResetToken nuevo, todo en una única
    transacción. El envío real del correo (enviar_email_recuperacion) es
    un punto de integración aparte, sin proveedor configurado todavía —
    no altera la lógica de seguridad, y cualquier falla suya se aísla por
    completo de la respuesta HTTP."""
    email = data.email.lower()
    usuario = db.query(Usuario).filter(Usuario.email == email).first()

    if usuario is not None and usuario.activo:
        ahora = datetime.utcnow()

        # Invalidar enlaces de recuperación anteriores sin usar: solo el
        # más reciente debe poder utilizarse.
        db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.usuario_id == usuario.id,
                PasswordResetToken.usado == False,
            )
            .values(usado=True, fecha_uso=ahora)
        )

        token = crear_sesion_reset(db, usuario.id)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        # Aislada de la respuesta HTTP: una futura falla del proveedor de
        # correo nunca debe cambiar el status ni el mensaje devuelto, ni
        # revelar detalles del proveedor al cliente.
        try:
            enviar_email_recuperacion(usuario.email, token)
        except Exception:
            pass

    return schemas.LogoutResponse(
        mensaje="Si el correo existe, se enviarán instrucciones de recuperación"
    )


@router.post("/restablecer", response_model=schemas.LogoutResponse)
def restablecer(data: schemas.RestablecerPasswordRequest, db: Session = Depends(get_db)):
    """Consume atómicamente un token de recuperación de un solo uso y
    establece una nueva contraseña. Revoca todas las sesiones anteriores
    del usuario (RefreshToken + invalidación de access tokens vía
    token_version) y marca cualquier otro enlace de recuperación
    pendiente como usado. Nunca reactiva una cuenta desactivada."""
    token_hash = hash_token_reset(data.token)
    ahora = datetime.utcnow()

    # Consumo atómico: mismo patrón que la rotación de /auth/refresh — un
    # único UPDATE condicional, sin ventana entre "verificar" y "actuar".
    resultado = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.usado == False,
            PasswordResetToken.fecha_expiracion > ahora,
        )
        .values(usado=True, fecha_uso=ahora)
    )

    if resultado.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_RESET_INVALIDO_MSG)

    sesion = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    usuario = sesion.usuario

    if usuario is None or not usuario.activo:
        # El token queda consumido igual (ya no reutilizable) aunque se
        # rechace el cambio; el restablecimiento nunca reactiva una
        # cuenta desactivada.
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_RESET_INVALIDO_MSG)

    usuario.password_hash = hash_password(data.nueva_password)
    usuario.token_version += 1

    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.usuario_id == usuario.id,
            RefreshToken.revocado == False,
        )
        .values(revocado=True, fecha_revocacion=ahora)
    )

    # Cualquier otro enlace de recuperación pendiente de este usuario
    # queda inutilizado (el que ya se consumió arriba no vuelve a
    # matchear porque su `usado` ya quedó en True en esta misma transacción).
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.usuario_id == usuario.id,
            PasswordResetToken.usado == False,
        )
        .values(usado=True, fecha_uso=ahora)
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return schemas.LogoutResponse(mensaje="Contraseña actualizada correctamente")


@router.get("/me", response_model=schemas.UsuarioResponse)
def me(usuario_actual: Usuario = Depends(get_usuario_actual)):
    return usuario_actual
