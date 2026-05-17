"""Eventos de configuración tenant: revisión y publicación Redis."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.db.models.company import Company
from app.services.tenant_config_events import (
    CONFIG_REVISION_KEY,
    bump_company_config_revision,
    bump_global_config_revision,
    publish_company_event,
    read_company_config_revision,
    read_global_config_revision,
    TenantConfigReason,
)


def _company() -> Company:
    c = Company(name="Test", nit_rut="900111222", address="Addr")
    c.settings_json = {}
    return c


def test_bump_company_config_revision_increments():
    company = _company()
    assert read_company_config_revision(company) == 0
    r1 = bump_company_config_revision(company)
    r2 = bump_company_config_revision(company)
    assert r1 == 1
    assert r2 == 2
    assert company.settings_json[CONFIG_REVISION_KEY] == 2


@patch("app.services.tenant_config_events.get_sync_redis")
def test_publish_company_event_calls_redis(mock_get_redis):
    mock_client = MagicMock()
    mock_get_redis.return_value = mock_client
    company_id = uuid4()
    publish_company_event(company_id, TenantConfigReason.SESSION_POLICY, 3)
    mock_client.publish.assert_called_once()
    channel, payload = mock_client.publish.call_args[0]
    assert str(company_id) in channel
    assert "tenant.config_changed" in payload
    assert "session_policy" in payload


@patch("app.services.platform_config_service.save_config")
@patch("app.services.platform_config_service.load_config")
def test_bump_global_config_revision(mock_load, mock_save):
    mock_load.return_value = {
        "plans": {},
        "session": {},
        "meta": {"global_config_revision": 4},
    }
    rev = bump_global_config_revision()
    assert rev == 5
    saved = mock_save.call_args[0][0]
    assert saved["meta"]["global_config_revision"] == 5


@patch("app.services.platform_config_service.load_config")
def test_read_global_config_revision(mock_load):
    mock_load.return_value = {"meta": {"global_config_revision": 7}}
    assert read_global_config_revision() == 7
