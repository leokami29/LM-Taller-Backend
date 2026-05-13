# ADR-001: Login multi-tenant y database-per-tenant

## Estado

Aceptado (implementación en curso).

## Contexto

Con **una base de datos por taller** el backend ya no puede resolver `User` solo por `email` sin saber en qué Postgres buscar. El login debe identificar el **taller** antes de validar credenciales.

## Decisión

1. **Login tenant**: estrategia **slug + email** (y contraseña).
   - El cliente envía `tenant_slug` (único global, almacenado en el catálogo) junto con `email` y `password`.
   - El servidor consulta el **catálogo** para obtener la URL de la BD del taller, abre sesión en esa BD y ejecuta la autenticación existente.

2. **Modo compatibilidad**: con `USE_TENANT_DATABASE_ROUTING=false` (por defecto), el comportamiento es el monolito actual: una sola `DATABASE_URL` y `tenant_slug` no es obligatorio.

3. **Unicidad de email**: por taller sigue aplicando `uq_users_company_email`. Entre talleres pueden repetirse emails; el slug desambigúa en login.

## Alternativas consideradas

- **Email global único en catálogo**: menos fricción UX; exige registro central de identidades.
- **Subdominio** (`taller.midominio.com`): mejor UX a escala; mayor coste de DNS, certificados y routing en edge.

## Consecuencias

- El frontend debe enviar `tenant_slug` cuando el despliegue active routing por tenant.
- Hay que provisionar filas en `tenant_routing` (catálogo) para cada taller antes de que los usuarios puedan iniciar sesión en modo routing.
