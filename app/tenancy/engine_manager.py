"""Pool LRU de engines SQLAlchemy por URL de tenant."""

from __future__ import annotations

import logging
from collections import OrderedDict
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings
from app.tenancy.metrics import record_engine_eviction

logger = logging.getLogger(__name__)


class TenantEngineManager:
    """LRU acotado de engines SQLAlchemy por URL (una URL ~ un tenant)."""

    def __init__(self, max_engines: int) -> None:
        self._max = max(1, max_engines)
        self._engines: OrderedDict[str, Engine] = OrderedDict()
        self._lock = Lock()

    def get_engine(self, database_url: str) -> Engine:
        with self._lock:
            if database_url in self._engines:
                self._engines.move_to_end(database_url)
                return self._engines[database_url]
            while len(self._engines) >= self._max:
                old_url, old_eng = self._engines.popitem(last=False)
                try:
                    old_eng.dispose()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Engine dispose falló: %s", exc)
                record_engine_eviction()
            eng = create_engine(
                database_url,
                echo=settings.DEBUG,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=5,
            )
            self._engines[database_url] = eng
            self._engines.move_to_end(database_url)
            return eng


tenant_engine_manager = TenantEngineManager(settings.TENANT_ENGINE_CACHE_MAX)
