import os
from datetime import timedelta
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
import base64

from app.core.dt import utc_now
from app.core.enums import PlanTier, SubscriptionStatus
from app.services.license_signing import sign_manifest_payload, verify_manifest_signature


def _ensure_test_keys() -> None:
    if os.getenv("LICENSE_SIGNING_PRIVATE_KEY_B64"):
        return
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    os.environ["LICENSE_SIGNING_PRIVATE_KEY_B64"] = base64.b64encode(
        private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode()
    os.environ["LICENSE_SIGNING_PUBLIC_KEY_B64"] = base64.b64encode(
        public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()


def test_sign_and_verify_manifest_roundtrip():
    _ensure_test_keys()
    payload = {
        "company_id": str(uuid4()),
        "tenant_slug": "demo-central",
        "plan": PlanTier.PRO.value,
        "subscription_status": SubscriptionStatus.ACTIVE.value,
        "issued_at": utc_now().isoformat(),
    }
    sig = sign_manifest_payload(payload)
    assert verify_manifest_signature(payload, sig)


def test_subscription_block_reason_suspended():
    from app.core.subscription_lifecycle import subscription_block_reason, subscription_is_usable

    assert not subscription_is_usable(SubscriptionStatus.SUSPENDED, utc_now() + timedelta(days=30))
    assert subscription_block_reason(SubscriptionStatus.SUSPENDED, utc_now() + timedelta(days=30)) == "status"
