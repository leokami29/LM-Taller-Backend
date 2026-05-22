from __future__ import annotations

from typing import Any, Iterable


def apply_allowed_updates(obj: Any, data: dict[str, Any], allowed_keys: Iterable[str]) -> None:
    for key in allowed_keys:
        if key in data:
            setattr(obj, key, data[key])
