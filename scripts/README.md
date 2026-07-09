# Scripts del backend

Ejecutar desde la carpeta `Backend` con el venv activo: `python -m scripts.<nombre>`.

## Operativos (uso diario / CI)

| Script | Descripción |
|--------|-------------|
| `migrate.py` | Migraciones tenant y catálogo (`tenant`, `catalog`, `all`, `diagnose`) |
| `migrate_all_tenant_databases.py` | Aplica migraciones a cada BD de taller (`--from-env-map`) |
| `seed_demo.py` | Taller demo principal + segundo tenant + usuarios plataforma |
| `seed_platform_super_admin.py` | Mínimo: solo super_admin de plataforma |
| `seed_platform.py` | Usuarios de plataforma (super, support, billing) |
| `generate_license_keys.py` | Genera par de claves Ed25519 para manifiestos de licencia |

## Desarrollo / datos de prueba

| Script | Descripción |
|--------|-------------|
| `seed_demo_primary.py` | Solo empresa demo principal |
| `seed_demo_routed.py` | Seed con routing multi-BD |
| `seed_demo_scenarios.py` | Escenarios adicionales de demo |
| `seed_demo_rbac.py` | Datos RBAC para demos |
| `seed_demo_constants.py` | Constantes compartidas por seeds |
| `seed_utils.py` | Utilidades internas de seeds (no invocar directamente) |
| `export_company_to_tenant_db.py` | Exporta empresa a BD tenant separada |

## One-offs históricos (evitar salvo migración puntual)

| Script | Descripción |
|--------|-------------|
| `apply_migration_019.py` | Aplicación manual de revisión 019 |
| `force_migration_019.py` | Forzar estado de migración 019 |
| `fix_alembic_and_upgrade_018.py` | Reparación de `alembic_version` + upgrade 018 |

Si un one-off ya no aplica a tu entorno, preferir `python -m scripts.migrate tenant` o `diagnose`.
