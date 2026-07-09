# ADR-002: Límites de módulos y capas

## Estado

Aceptado.

## Contexto

El backend crece en endpoints, servicios y lógica multi-tenant. Sin convenciones explícitas, la capa HTTP acumula queries SQL y los módulos superan 500+ líneas, dificultando pruebas y cambios.

## Decisión

Organizar el código por **capas técnicas** (no por dominio de negocio top-level) con estas reglas:

### `app/core/`

Lógica **pura sin I/O**: enums, utilidades de fecha (`dt`), validación RUT, reglas de estado, constantes de permisos, excepciones de dominio.

- Sin imports de `sqlalchemy`, `redis`, `fastapi` ni sesiones de DB.
- Ejemplos: `enums.py`, `dt.py`, `rut.py`, `subscription_lifecycle.py`, `permissions.py`.

### `app/services/`

**Orquestación con efectos secundarios**: DB, Redis, email, PDF, firmas de licencia.

- Reciben `Session` (u otros clientes) como argumento; no definen rutas HTTP.
- Un archivo por concepto de negocio (`order_service.py`, `inventory_service.py`).
- Paquetes anidados solo para subdominios genuinos (p. ej. `services/sync_admin/`).

### `app/api/`

Solo **HTTP**: routers, `Depends`, códigos de estado, mapeo request/response.

- Delegar reglas de negocio a `services/`.
- Evitar `db.query()` en endpoints; excepciones puntuales deben justificarse.
- Dependencias de auth en `app/api/deps/`; `app/dependencies.py` es shim de compatibilidad.

### `app/schemas/`

Todos los modelos **Pydantic** expuestos o compartidos entre capas.

- No definir `BaseModel` en endpoints salvo DTOs efímeros de un solo uso interno.

### `app/db/`

Modelos SQLAlchemy, sesiones, RLS y catálogo (`db/catalog/`).

### `app/repositories/` (opcional)

Introducir solo cuando la misma consulta (filtros `company_id`, paginación, joins) se repita en **3+ lugares**.

### Dependencias permitidas

```
api → services, schemas, core, api/deps
services → db, schemas, core, infrastructure, tenancy
core → (solo stdlib y otros core)
db → core (mínimo)
```

La API **no** debe importar `db.models` salvo casos documentados (p. ej. tipos en firmas de Depends legacy).

### Interfaces públicas

Paquetes expuestos a otros módulos deben declarar `__all__` en su `__init__.py`. Lo no listado es detalle de implementación.

## Alternativas consideradas

- **Estructura domain-driven** (`app/domains/orders/`): mejor aislamiento por negocio, pero costo alto de migración para el tamaño actual del equipo.
- **Repositorios obligatorios**: más capas; pospuesto hasta detectar duplicación real de queries.

## Consecuencias

- Refactors priorizan adelgazar endpoints (`sync_admin`, `orders`) moviendo lógica a services.
- Nuevos endpoints deben seguir el flujo: router → service → ORM.
- Tests de integración HTTP siguen en `tests/`; tests unitarios de services pueden añadirse junto a la lógica extraída.
