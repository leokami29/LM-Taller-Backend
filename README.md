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

## Estructura

- `app/main.py`: aplicación FastAPI.
- `app/api/v1/`: routers versionados.
- `app/db/models/`: modelos SQLAlchemy.
- `app/schemas/`: modelos Pydantic v2.
- `app/services/`: reglas de negocio (órdenes, inventario, analítica).
- `migrations/`: Alembic.
