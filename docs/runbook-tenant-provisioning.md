# Alta de taller (database-per-tenant)

## Prerrequisitos

1. Postgres del **catálogo** creado y migrado: `alembic -c alembic_catalog.ini upgrade head`.
2. Postgres del **tenant** vacío (o restaurado) con el mismo esquema: `alembic upgrade head` contra su `DATABASE_URL`.
3. Variables en el servicio backend: `USE_TENANT_DATABASE_ROUTING=true`, `CATALOG_DATABASE_URL`, y opcionalmente `TENANT_DATABASE_URL_MAP_JSON` para pruebas rápidas.

## Checklist

1. Generar `company_id` (UUID) coherente entre catálogo y data plane (la API de plataforma lo hace al crear empresa con routing activo).
2. Insertar fila en `tenant_routing` (slug único, `database_url`, columnas denormalizadas para listados).
3. Ejecutar seed de datos mínimos en la BD del tenant si aplica.
4. `python -m scripts.seed_platform_super_admin` contra el **catálogo** si aún no hay `platform_users`, o `python -m scripts.seed_demo` con routing activo (semilla catálogo + `tenant_routing` + ambas BDs tenant según `TENANT_DATABASE_URL_MAP_JSON`).
5. Smoke: login tenant con `tenant_slug` + email + contraseña; login plataforma en `/api/platform/v1/auth/login`.

## Objetivo de tiempo (definir con negocio)

| Paso | Notas |
|------|--------|
| Crear Postgres tenant | Depende del proveedor (Railway: minutos). |
| `alembic upgrade head` | Incluir en pipeline; ver `scripts/migrate_all_tenant_databases.py`. |
| Fila `tenant_routing` + smoke login | Manual vía API plataforma o SQL controlado. |

Meta operativa sugerida: **&lt; 30 min** de trabajo humano una vez automatizado el aprovisionamiento de instancia.

## Automatización y CI

- Objetivo: Terraform / Railway template / script interno que cree el plugin Postgres del tenant, ejecute migraciones y llame a `POST /api/platform/v1/companies` con `tenant_slug` y `tenant_database_url`.
- En CI: job opcional que, contra BDs de laboratorio, ejecute `alembic -c alembic_catalog.ini upgrade head` y `alembic upgrade head` sobre una lista de URLs (misma lista que usa `migrate_all_tenant_databases.py`) tras merge a `main`.
