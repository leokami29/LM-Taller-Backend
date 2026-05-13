# Backup y restauración por tenant

## Objetivos

- **RPO/RTO** por taller acordados con el negocio (p. ej. backup diario, restauración en &lt; 1 h).
- Credenciales de Postgres del tenant almacenadas como referencia en el catálogo; rotación con **ventana dual** (dos URLs válidas brevemente) al rotar contraseña en el proveedor.

### Plantilla RPO/RTO (rellenar por tenant crítico)

| Tenant (slug) | RPO aceptable | RTO aceptable | Backup PITR | Última prueba restore |
|---------------|---------------|---------------|-------------|----------------------|
| _ejemplo_     | 24 h          | 4 h           | Sí / No   | _fecha_              |

### Rotación dual de secretos

1. Crear nueva credencial en el proveedor y nueva URL (o misma URL con password nuevo según política).
2. Actualizar `tenant_routing.database_url` en catálogo **manteniendo** brevemente acceso con credencial antigua si el proxy lo permite, o programar ventana de mantenimiento.
3. Revocar credencial antigua tras verificar smoke (login tenant + una lectura/escritura trivial).

## Railway / Postgres gestionado

1. Activar backups automáticos del plugin Postgres de **cada** BD de tenant y del **catálogo**.
2. Probar restauración a un entorno aislado al menos trimestralmente.
3. Documentar quién autoriza restore y cómo se actualiza `tenant_routing.database_url` si el host cambia tras restore.

## MinIO / S3

Ver [storage-tenant-boundaries.md](storage-tenant-boundaries.md): los objetos deben ir bajo prefijo `companies/{company_id}/` (o equivalente) para no cruzar datos entre tenants.
