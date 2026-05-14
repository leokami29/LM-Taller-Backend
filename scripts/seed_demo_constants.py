"""Constantes compartidas para la semilla demo (taller principal + norte)."""

from uuid import UUID

# UUID fijos para laboratorio database-per-tenant (deben coincidir con TENANT_DATABASE_URL_MAP_JSON).
DEMO_CENTRAL_COMPANY_ID = UUID("a0000000-0000-4000-8000-000000000001")
DEMO_NORTE_COMPANY_ID = UUID("a0000000-0000-4000-8000-000000000002")
DEMO_CENTRAL_SLUG = "demo-central"
DEMO_NORTE_SLUG = "demo-norte"

DEMO_NIT = "901-DEMO-SG"
SECOND_DEMO_NIT = "902-DEMO-SG2"
SECOND_COMPANY_NAME = "Taller Norte Demo SG"
DEMO_EMAIL_DOMAIN = "demo.sgtaller.com"
DEMO_PASSWORD = "Demo1234"
DEMO_NITS = (DEMO_NIT, SECOND_DEMO_NIT)
