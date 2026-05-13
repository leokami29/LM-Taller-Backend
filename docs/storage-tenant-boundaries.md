# Límites de almacenamiento por tenant (MinIO / S3)

## Recomendación

- Bucket **compartido** con prefijo obligatorio por empresa, por ejemplo: `sgtaller/companies/{company_id}/...`
- Las URLs firmadas deben incluir el prefijo del objeto; no aceptar rutas arbitrarias desde el cliente.
- Al mover a database-per-tenant, el **aislamiento lógico** en archivos sigue siendo necesario: una BD por taller no sustituye el control de acceso en object storage.

## Helper en código

- `app.core.tenant_storage_paths.tenant_storage_prefix(company_id)` devuelve la raíz `sgtaller/companies/{uuid}` (sin barra final); concatenar segmentos relativos con `/` al construir la key completa.
- Usar ese prefijo en todos los uploads de PDFs y adjuntos cuando el bucket sea compartido.
