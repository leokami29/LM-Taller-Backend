import os
import tempfile

from sqlalchemy import text

from app.tenancy import TenantEngineManager


def test_tenant_engine_manager_lru_bounded():
    """Con max=2, al pedir varias URLs distintas el LRU evicta sin lanzar."""
    mgr = TenantEngineManager(2)
    files = [tempfile.NamedTemporaryFile(delete=False, suffix=".db") for _ in range(4)]
    try:
        urls = [f"sqlite:///{f.name}" for f in files]
        for url in urls:
            eng = mgr.get_engine(url)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            assert eng is not None
    finally:
        for f in files:
            f.close()
            try:
                os.unlink(f.name)
            except OSError:
                pass
