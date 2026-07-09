"""Shim de compatibilidad: re-exporta dependencias desde app.api.deps."""

from app.api.deps import *  # noqa: F403
from app.api.deps import __all__ as __all__
