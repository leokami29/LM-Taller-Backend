"""Genera par Ed25519 para LICENSE_SIGNING_* en .env (desarrollo)."""

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

private = Ed25519PrivateKey.generate()
public = private.public_key()
priv_b64 = base64.b64encode(
    private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
).decode()
pub_b64 = base64.b64encode(public.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
print(f"LICENSE_SIGNING_PRIVATE_KEY_B64={priv_b64}")
print(f"LICENSE_SIGNING_PUBLIC_KEY_B64={pub_b64}")
