# SGtaller Web — Backend (FastAPI)

API REST modular para gestión de centros de servicio técnico (multi-tenant por `company_id`).

## Requisitos

- Python 3.11+
- PostgreSQL 15+ (recomendado vía Docker Compose)

## Arranque rápido

**Importante (Windows):** usa un entorno virtual y el `python` de ese venv. Si instalas en el Python del sistema, `alembic` puede no encontrarse o faltan ruedas para tu versión de Python.

Se recomienda **Python 3.12 o 3.13** con el venv del proyecto:

```powershell
cd Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
# Edita .env con tu DATABASE_URL (p. ej. Railway)
# Opcional en local:
# docker compose up -d postgres
python -m scripts.migrate tenant
# Si usas catálogo separado (USE_TENANT_DATABASE_ROUTING + CATALOG_DATABASE_URL):
# python -m scripts.migrate catalog
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Equivalente manual: `python -m alembic upgrade head` (tenant) y `python -m alembic -c alembic_catalog.ini upgrade head` (catálogo). **No** uses `migrations_catalog/alembic.ini` (no existe); el archivo es `alembic_catalog.ini` en la raíz de `Backend`.

Con **`USE_TENANT_DATABASE_ROUTING=true`** y `DATABASE_URL` igual a `CATALOG_DATABASE_URL` (solo catálogo para rutas globales): migrá cada taller con  
`python -m scripts.migrate_all_tenant_databases --from-env-map` — este comando **carga `Backend/.env` solo** y no necesitás exportar `TENANT_DATABASE_URL_MAP_JSON` en PowerShell. Opción todo-en-uno: `python -m scripts.migrate all`.

Si ves `No module named alembic`, casi siempre es que no activaste el venv o no corriste `pip install -r requirements.txt` en ese mismo Python.

### Error `Can't locate revision identified by 'catalog_001'`

Significa que la base apuntada por `DATABASE_URL` tiene en `alembic_version` una revisión del **catálogo**, no del tenant. Suele pasar si `DATABASE_URL` y `CATALOG_DATABASE_URL` apuntan a la misma BD o si corriste migraciones de catálogo contra la BD del taller.

```powershell
python -m scripts.migrate diagnose
```

No hagas `alembic stamp` sobre la BD **catálogo** si `DATABASE_URL` es intencionalmente la misma que `CATALOG_DATABASE_URL`; ahí la versión `catalog_*` es correcta.

Si la BD tenant quedó mal etiquetada (ya tiene tablas de app pero versión `catalog_001`):

```powershell
python -m alembic stamp 009_customer_search_idx
python -m scripts.migrate tenant
```

Luego, en la BD **catálogo** (con `CATALOG_DATABASE_URL` en `.env`):

```powershell
python -m scripts.migrate catalog
```

Documentación interactiva: `http://localhost:8000/docs`

## Variables de entorno

Ver [.env.example](.env.example). Destacadas:

- `DATABASE_URL`: cadena SQLAlchemy/Postgres.
- `SECRET_KEY`: clave para firmar JWT (obligatoria en producción).
- `CORS_ORIGINS`: lista separada por comas o JSON.
- Opcional **database-per-tenant**: `USE_TENANT_DATABASE_ROUTING`, `CATALOG_DATABASE_URL`, `TENANT_DATABASE_URL_MAP_JSON` (ver [.env.example](.env.example)). Migraciones del catálogo: `python -m alembic -c alembic_catalog.ini upgrade head`. ADR: [docs/adr/ADR-001-tenant-login-and-database-per-tenant.md](docs/adr/ADR-001-tenant-login-and-database-per-tenant.md).

### PostgreSQL en Railway

1. En Railway, abre el plugin **Postgres** y copia la **URL pública** (o la variable `DATABASE_URL` que te genera).
2. En tu máquina, pega esa URL en el archivo **`.env`** (no en `.env.example`; `.env` no se sube a git). Para conexiones por el proxy público suele hacer falta SSL:

   `postgresql://USER:PASSWORD@HOST:PORT/railway?sslmode=require`

3. Aplica migraciones contra esa base (desde la carpeta `Backend`, con el entorno activo y dependencias instaladas):

   ```bash
   python -m alembic upgrade head
   ```

4. Si despliegas la API **también en Railway**, define las mismas variables en el servicio (pestaña **Variables**): `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`, etc. No pegues secretos en el repositorio.

**Seguridad:** si la URL o la contraseña se compartieron en un chat o issue, conviene **rotar la contraseña** del usuario de Postgres en Railway y actualizar `DATABASE_URL`.

## Docker (API + Postgres + Redis + MinIO)

```bash
docker compose up --build
```

La API espera a que Postgres esté sano, aplica migraciones y levanta Uvicorn en el puerto 8000.

## Autenticación

### Empresa (taller) — `/api/v1`

- `POST /api/v1/auth/login` (JSON: `email`, `password`, y con routing por tenant activo también `tenant_slug`) devuelve `access_token`, `refresh_token` y `user`.
- `POST /api/v1/auth/refresh` (JSON: `refresh_token`) rota el par de tokens.
- `POST /api/v1/auth/token` (OAuth2 password flow para Swagger: `username` = email; con routing por tenant añadir query `tenant_slug=...`).
- `GET /api/v1/auth/me` con cabecera `Authorization: Bearer <access_token>`.

Los JWT de empresa incluyen `typ=tenant` y `company_id` firmado; no aceptes `company_id` enviado por el cliente para filtrar datos.

### Plataforma (licenciante) — `/api/platform/v1`

- `POST /api/platform/v1/auth/login` y `POST /api/platform/v1/auth/token` (mismo esquema que arriba).
- `POST /api/platform/v1/auth/refresh` con `refresh_token` de plataforma.
- Caducidad de sesiones (persistida en `platform_config.json`, editable desde el front en `/platform/settings`):
  - `GET /api/platform/v1/config/session` — lectura (roles con permiso de companies read).
  - `PUT /api/platform/v1/config/session` — solo `super_admin`; cuerpo: `tenant_access_token_minutes`, `tenant_refresh_token_days`, `platform_access_token_minutes`, `platform_refresh_token_days` (access: 15–1440 min, refresh: 1–90 días). Aplica en el **próximo login** o cuando el refresh emita tokens nuevos. Si no hay archivo, se usan `ACCESS_TOKEN_EXPIRE_MINUTES` y `REFRESH_TOKEN_EXPIRE_DAYS` del `.env`.
- **Overrides por taller** (en `companies.settings_json.session_policies`, precedencia: usuario > sede > empresa > global):
  - Plataforma: `GET/PUT /api/platform/v1/companies/{id}/session-policy`, `PUT/DELETE .../sites/{site_id}`, `PUT/DELETE .../users/{user_id}`, `GET .../users`. `PUT` de empresa admite `apply_to_all_sites: true` para quitar overrides de sede.
  - Admin taller: `GET/PUT /api/v1/admin/session-policy` y rutas análogas bajo `/sites/{id}` y `/users/{id}` (permiso `admin:users`).
  - Refresh tenant: body opcional `site_id` para resolver TTL por sede activa.
- Gestión de empresas: `GET/PATCH/POST /api/platform/v1/companies/...` (permisos según rol de plataforma).
- `POST /api/platform/v1/impersonate` (solo `super_admin`): devuelve tokens con `act_as_company_id` para operar con el contexto RLS de esa empresa; queda registro en `audit_logs`.

Semilla **solo** del super_admin (equivalente a lo mínimo de plataforma): `python -m scripts.seed_platform_super_admin`.

Para **taller demo + segundo tenant + tres roles de plataforma** (recomendado para probar multi-tenant y el front `/platform`): usa `seed_demo` (abajo).

## Multi-tenant y frontend

- **Glosario**: *Tenant* = empresa que paga el SaaS (`Company`); *cliente del taller* = `Customer`; *plataforma* = equipo licenciante (`PlatformUser`).
- **Resolución de tenant en el navegador**: conviene fijar el contexto con **subdominio** (`empresa.tudominio.com`) o **prefijo de ruta** (`/t/{slug}/...`). Tras login, guarda el `company_id` solo desde la respuesta del servidor (o dedúcelo del subdominio acordado), nunca desde un parámetro arbitrario del usuario.
- **Tokens**: guarda `access_token` y `refresh_token` por “modo” (empresa vs plataforma) y por tenant activo. Al cambiar de empresa o de subdominio, **borra el estado** de cliente (caché, stores tipo Zustand/Redux, React Query) y vuelve a cargar datos con el nuevo token.
- **Rutas**: el panel de plataforma debería vivir en rutas separadas (`/platform/...`) con layout y guards distintos a la app de taller (`/api/v1` vs `/api/platform/v1`).

## Semilla manual (desarrollo)

Tras migrar, inserta una empresa y un usuario administrador (ajusta email y hash si usas otro flujo):

```sql
-- Ejemplo conceptual: usar la app o un script Python con SecurityUtils.hash_password
```

Recomendado: crear empresa y admin vía SQLAlchemy en un script local o usar los tests como referencia (`tests/conftest.py`).

## Tests

Requiere Postgres accesible con la misma `DATABASE_URL` que uses en `.env`:

```bash
python -m alembic upgrade head
pytest -q
```

Los tests recrean el esquema en cada caso (drop/create) sobre la base configurada; **no** uses una base de datos con datos que quieras conservar.

## Datos de demostración (frontend / Railway)

Tras `alembic upgrade head`, pobla Postgres con el taller demo principal (**NIT 901-DEMO-SG**), un **segundo tenant** (**902-DEMO-SG2**, orden y datos mínimos para pruebas de aislamiento) y usuarios de **plataforma** (`super_admin`, `support_readonly`, `billing`):

```powershell
.\.venv\Scripts\Activate.ps1
python -m scripts.seed_demo
```

Si la empresa principal ya existe, el script **no** la recrea, pero sí intenta crear el tenant secundario y asegura los usuarios de plataforma. Para **borrar y volver a crear** ambas empresas demo:

```powershell
python -m scripts.seed_demo --force
```

Contraseña de los usuarios **taller** demo: **`Demo1234`**. Usuarios **plataforma** por defecto en dev: `super@sgtaller.com` / `DevSuper1234` (y roles `support_readonly` / `billing`; ver [`scripts/seed_platform.py`](scripts/seed_platform.py) y el docstring de [`scripts/seed_demo.py`](scripts/seed_demo.py)).

## Tiempo real (configuración y licencias)

Los cambios hechos desde la **consola de plataforma** (suscripción, revocación de puesto, planes globales) se propagan a clientes conectados vía **Redis pub/sub** + **SSE**:

1. Plataforma persiste el cambio y llama `post_company_mutation` / `bump_and_notify_global` ([`app/services/tenant_config_events.py`](app/services/tenant_config_events.py)).
2. Publica en canales `tenant:events:{company_id}` y `tenant:events:global`.
3. Los clientes con JWT de **usuario del taller** abren `GET /api/v1/events/stream` ([`app/api/v1/endpoints/tenant_events.py`](app/api/v1/endpoints/tenant_events.py)).
4. **Web tenant** refresca permisos/sesión; **DesktopLM** llama `POST /license/refresh` en la API local.

**Requisitos en desarrollo:**

```powershell
docker compose up -d redis
# REDIS_URL=redis://localhost:6379 en .env
```

`GET /health` incluye `redis: ok|degraded`. Sin Redis, el SSE sigue vivo pero solo envía heartbeats (sin eventos).

Los módulos/límites efectivos del manifiesto se resuelven desde el **catálogo** ([`app/services/effective_entitlements_service.py`](app/services/effective_entitlements_service.py)), no solo desde `companies.settings_json`.

**Checklist E2E rápido:** cambiar suscripción en `/platform` → toast en web tenant y licencia actualizada en desktop (&lt;5 s con Redis). Revocar puesto → desktop bloqueado tras refresh. Editar plan global en settings → manifiesto con nuevos módulos sin re-asignar suscripción.

## Estructura

```
app/
├── main.py              # FastAPI, middleware, lifespan
├── config.py            # Settings (pydantic-settings)
├── dependencies.py      # Shim → app/api/deps (compatibilidad)
├── api/
│   ├── deps/            # Auth tenant, plataforma, portal, permisos
│   ├── v1/endpoints/    # API taller (/api/v1)
│   └── platform/v1/     # API plataforma (/api/platform/v1)
├── core/                # Lógica pura: enums, permisos, reglas de estado
├── services/            # Negocio con I/O (DB, Redis, PDF, email)
├── schemas/             # Pydantic v2
├── db/
│   ├── models/          # SQLAlchemy tenant
│   ├── catalog/         # Modelos y sesión del catálogo global
│   └── session.py       # get_db, tenant routing
├── tenancy/             # Resolución URL por tenant, engines LRU
├── middleware/          # Logging, headers, errores
└── infrastructure/      # Redis y clientes externos
migrations/              # Alembic tenant
migrations_catalog/      # Alembic catálogo
scripts/                 # Ver scripts/README.md
tests/                   # pytest (paralelo a app/)
docs/adr/                # Decisiones de arquitectura (ADR-001, ADR-002)
```

**Flujo de dependencias:** `api` → `services` → `db`; `core` no importa capas superiores. Convenciones detalladas: [docs/adr/ADR-002-module-boundaries.md](docs/adr/ADR-002-module-boundaries.md).
