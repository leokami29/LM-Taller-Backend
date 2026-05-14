# Laboratorio Railway: 3 bases de datos

Asignación recomendada cuando probáis **database-per-tenant**:

| Plugin Postgres (Railway) | Variable en el servicio API | Uso |
|---------------------------|-----------------------------|-----|
| BD 1 | `CATALOG_DATABASE_URL` | Catálogo: `tenant_routing`, `platform_users` (solo con routing activo), `catalog_audit_logs`. |
| BD 2 | Valor dentro de `TENANT_DATABASE_URL_MAP_JSON` para el UUID de la empresa A | Data plane taller A (mismo esquema Alembic que el monolito). |
| BD 3 | Otro valor en el mismo JSON para el UUID de la empresa B | Data plane taller B. |

1. Aplicar migraciones del **catálogo** contra BD1: `alembic -c alembic_catalog.ini upgrade head`.
2. Aplicar migraciones del **esquema de taller** contra BD2 y BD3: `python -m scripts.migrate_all_tenant_databases --urls "URL_BD2,URL_BD3"`.
3. Insertar filas en `tenant_routing` (slug, `company_id`, `database_url`) coherentes con los seeds de cada tenant, o usar `python -m scripts.seed_demo` (con `USE_TENANT_DATABASE_ROUTING=true` y `TENANT_DATABASE_URL_MAP_JSON` usando los UUID de `scripts/seed_demo_constants.py`).
4. Activar `USE_TENANT_DATABASE_ROUTING=true` y reiniciar el backend.
5. Verificar `/health`: con routing activo incluye `tenant_resolution_metrics` (resoluciones, cache hits, evicciones del pool LRU) para depuración sin PII.
