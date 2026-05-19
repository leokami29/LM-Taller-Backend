"""Firma y verificación Ed25519 de manifiestos de licencia desktop."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_KEY_ID = "v1"


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _signing_private_key_b64() -> str:
    return (
        os.getenv("LICENSE_SIGNING_PRIVATE_KEY_B64", "").strip()
        or settings.LICENSE_SIGNING_PRIVATE_KEY_B64.strip()
    )


def _signing_public_key_b64() -> str:
    return (
        os.getenv("LICENSE_SIGNING_PUBLIC_KEY_B64", "").strip()
        or settings.LICENSE_SIGNING_PUBLIC_KEY_B64.strip()
    )


def _load_private_key() -> Ed25519PrivateKey | None:
    raw = _signing_private_key_b64()
    if not raw:
        return None
    try:
        key_bytes = base64.b64decode(raw)
        return Ed25519PrivateKey.from_private_bytes(key_bytes)
    except Exception:
        logger.exception("LICENSE_SIGNING_PRIVATE_KEY_B64 invalid")
        return None


def load_public_key() -> Ed25519PublicKey | None:
    raw = _signing_public_key_b64()
    if not raw:
        return None
    try:
        key_bytes = base64.b64decode(raw)
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    except Exception:
        logger.exception("LICENSE_SIGNING_PUBLIC_KEY_B64 invalid")
        return None


def ensure_dev_keypair() -> tuple[str, str]:
    """Genera par dev y lo loguea si no hay claves configuradas (solo desarrollo)."""
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    priv_b64 = base64.b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()
    pub_b64 = base64.b64encode(public.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    logger.warning(
        "LICENSE_SIGNING keys missing; generated DEV keys. "
        "Set LICENSE_SIGNING_PRIVATE_KEY_B64 and LICENSE_SIGNING_PUBLIC_KEY_B64 in .env"
    )
    return priv_b64, pub_b64


def sign_manifest_payload(payload: dict[str, Any], *, key_id: str = DEFAULT_KEY_ID) -> str:
    private = _load_private_key()
    if private is None:
        if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
            priv_b64, pub_b64 = ensure_dev_keypair()
            os.environ.setdefault("LICENSE_SIGNING_PRIVATE_KEY_B64", priv_b64)
            os.environ.setdefault("LICENSE_SIGNING_PUBLIC_KEY_B64", pub_b64)
            private = _load_private_key()
        if private is None:
            raise RuntimeError("LICENSE_SIGNING_PRIVATE_KEY_B64 is not configured")
    signature = private.sign(_canonical_json(payload))
    return base64.b64encode(signature).decode("ascii")


def verify_manifest_signature(payload: dict[str, Any], signature_b64: str) -> bool:
    public = load_public_key()
    if public is None:
        return False
    try:
        sig = base64.b64decode(signature_b64)
        public.verify(sig, _canonical_json(payload))
        return True
    except Exception:
        return False
