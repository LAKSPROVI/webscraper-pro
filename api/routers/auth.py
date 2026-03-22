"""
routers/auth.py — Autenticação JWT simples para ambiente inicial.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel, Field

SECRET_KEY = os.getenv("API_SECRET_KEY", os.getenv("SECRET_KEY", "change_me_in_production"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("API_ACCESS_TOKEN_EXPIRE_MINUTES", os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
)
ADMIN_USER = os.getenv("API_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("API_ADMIN_PASSWORD", "admin")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autenticar usuário e obter JWT",
)
async def login(payload: LoginRequest) -> TokenResponse:
    if payload.username != ADMIN_USER or payload.password != ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_at = datetime.now(tz=timezone.utc) + expires_delta

    token = jwt.encode(
        {
            "sub": payload.username,
            "exp": int(expire_at.timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return TokenResponse(
        access_token=token,
        expires_in=int(expires_delta.total_seconds()),
    )
