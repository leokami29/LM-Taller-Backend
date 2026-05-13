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
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Si ves `No module named alembic`, casi siempre es que no activaste el venv o no corriste `pip install -r requirements.txt` en ese mismo Python.

Documentación interactiva: `http://localhost:8000/docs`

## Variables de entorno

Ver [.env.example](.env.example). Destacadas:

- `DATABASE_URL`: cadena SQLAlchemy/Postgres.
- `SECRET_KEY`: clave para firmar JWT (obligatoria en producción).
- `CORS_ORIGINS`: lista separada por comas o JSON.

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

- `POST /api/v1/auth/login` (JSON: `email`, `password`) devuelve `access_token`, `refresh_token` y `user`.
- `POST /api/v1/auth/refresh` (JSON: `refresh_token`) rota el par de tokens.
- `POST /api/v1/auth/token` (OAuth2 password flow para Swagger: `username` = email).
- `GET /api/v1/auth/me` con cabecera `Authorization: Bearer <access_token>`.

Los JWT de empresa incluyen `typ=tenant` y `company_id` firmado; no aceptes `company_id` enviado por el cliente para filtrar datos.

### Plataforma (licenciante) — `/api/platform/v1`

- `POST /api/platform/v1/auth/login` y `POST /api/platform/v1/auth/token` (mismo esquema que arriba).
- `POST /api/platform/v1/auth/refresh` con `refresh_token` de plataforma.
- Gestión de empresas: `GET/PATCH/POST /api/platform/v1/companies/...` (permisos según rol de plataforma).
- `POST /api/platform/v1/impersonate` (solo `super_admin`): devuelve tokens con `act_as_company_id` para operar con el contexto RLS de esa empresa; queda registro en `audit_logs`.

Semilla del primer super_admin: `python -m scripts.seed_platform_super_admin`.

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

Tras `alembic upgrade head`, puedes poblar Postgres con un taller de prueba (usuarios, clientes, equipos, inventario, órdenes en varios estados, timeline, PDF de ejemplo):

```powershell
.\.venv\Scripts\Activate.ps1
python -m scripts.seed_demo
```

Para **borrar y volver a crear** esa empresa demo (NIT `901-DEMO-SG`):

```powershell
python -m scripts.seed_demo --force
```

Contraseña de todos los usuarios demo: **`Demo1234`**. Cuentas útiles: `admin@demo.sgtaller.com`, `recepcion@...`, `tecnico1@...`, `visitante@...` (ver docstring en [`scripts/seed_demo.py`](scripts/seed_demo.py)).

## Estructura

- `app/main.py`: aplicación FastAPI.
- `app/api/v1/`: routers versionados.
- `app/db/models/`: modelos SQLAlchemy.
- `app/schemas/`: modelos Pydantic v2.
- `app/services/`: reglas de negocio (órdenes, inventario, analítica).
- `migrations/`: Alembic.
