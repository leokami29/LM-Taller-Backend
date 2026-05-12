# SGtaller Web — Backend (FastAPI)

API REST modular para gestión de centros de servicio técnico (multi-tenant por `company_id`).

## Requisitos

- Python 3.11+
- PostgreSQL 15+ (recomendado vía Docker Compose)

## Arranque rápido

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
docker compose up -d postgres
alembic upgrade head
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva: `http://localhost:8000/docs`

## Variables de entorno

Ver [.env.example](.env.example). Destacadas:

- `DATABASE_URL`: cadena SQLAlchemy/Postgres.
- `SECRET_KEY`: clave para firmar JWT (obligatoria en producción).
- `CORS_ORIGINS`: lista separada por comas o JSON.

## Docker (API + Postgres + Redis + MinIO)

```bash
docker compose up --build
```

La API espera a que Postgres esté sano, aplica migraciones y levanta Uvicorn en el puerto 8000.

## Autenticación

- `POST /api/v1/auth/login` (JSON: `email`, `password`).
- `POST /api/v1/auth/token` (OAuth2 password flow para Swagger: `username` = email).
- `GET /api/v1/auth/me` con cabecera `Authorization: Bearer <token>`.

## Semilla manual (desarrollo)

Tras migrar, inserta una empresa y un usuario administrador (ajusta email y hash si usas otro flujo):

```sql
-- Ejemplo conceptual: usar la app o un script Python con SecurityUtils.hash_password
```

Recomendado: crear empresa y admin vía SQLAlchemy en un script local o usar los tests como referencia (`tests/conftest.py`).

## Tests

Requiere Postgres accesible con la misma `DATABASE_URL` que uses en `.env`:

```bash
alembic upgrade head
pytest -q
```

Los tests recrean el esquema en cada caso (drop/create) sobre la base configurada; **no** uses una base de datos con datos que quieras conservar.

## Estructura

- `app/main.py`: aplicación FastAPI.
- `app/api/v1/`: routers versionados.
- `app/db/models/`: modelos SQLAlchemy.
- `app/schemas/`: modelos Pydantic v2.
- `app/services/`: reglas de negocio (órdenes, inventario, analítica).
- `migrations/`: Alembic.
