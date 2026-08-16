// Fase 27 - valores no-secretos para el ambiente producción. Ver el
// comentario de cabecera de staging.bicepparam - misma disciplina (sin
// secretos, `apiImage`/`workerImage` sobrescritos por el workflow real).
// deploy-prod.yml solo se dispara manualmente en esta fase (sin
// auto-deploy sin piloto todavía, Fase 28) y requiere aprobación vía
// `environment: production` de GitHub (Settings del repo, fuera de
// alcance de código - plan §13/§16 Decisión recomendada #5).

using '../bicep/main.bicep'

param environmentName = 'production'
param location = 'eastus2'
param namePrefix = 'procurawise'

param apiImage = 'procurawiseacrproduction.azurecr.io/procurawise-api:placeholder'
param workerImage = 'procurawiseacrproduction.azurecr.io/procurawise-worker:placeholder'
// Fase 28 - mismo placeholder que api/worker, sobrescrito por deploy-prod.yml.
param webImage = 'procurawiseacrproduction.azurecr.io/procurawise-web:placeholder'

param storageContainerNames = [
  'procurawise-production'
  'procurawise-documents'
  'procurawise-reports'
]

param plainEnv = [
  { name: 'ENVIRONMENT', value: 'production' }
  { name: 'LOG_LEVEL', value: 'info' }
  { name: 'MONGODB_DB_NAME', value: 'procurawise_production' }
  { name: 'STORAGE_CONTAINER_NAME', value: 'procurawise-production' }
  { name: 'AZURE_STORAGE_API_VERSION', value: '2025-01-05' }
  { name: 'QUEUE_BACKEND', value: 'service_bus' }
  { name: 'JWT_ALGORITHM', value: 'HS256' }
  { name: 'ACCESS_TOKEN_TTL_MINUTES', value: '30' }
  { name: 'PRE_SESSION_TOKEN_TTL_MINUTES', value: '5' }
  { name: 'OIDC_MICROSOFT_TENANT', value: 'common' }
  { name: 'OIDC_MICROSOFT_CLIENT_ID', value: 'REPLACE_ME' }
  { name: 'OIDC_GOOGLE_CLIENT_ID', value: 'REPLACE_ME' }
  { name: 'OIDC_REDIRECT_BASE_URL', value: 'https://REPLACE_ME_API_FQDN' }
  { name: 'FRONTEND_BASE_URL', value: 'https://REPLACE_ME_FRONTEND_FQDN' }
  { name: 'AUDIT_EVENT_RETENTION_DAYS', value: '365' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: 'REPLACE_ME' }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: 'REPLACE_ME' }
  { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
  { name: 'AI_REQUEST_TIMEOUT_SECONDS', value: '30' }
  { name: 'AI_EXECUTION_RETENTION_DAYS', value: '365' }
  { name: 'AI_SCORE_SUGGESTION_ENABLED', value: 'true' }
  { name: 'FOUNDRY_WEB_SEARCH_ENABLED', value: 'false' }
  { name: 'VENDOR_INVITATION_TTL_DAYS', value: '7' }
  { name: 'TRUSTED_PROXY_HOPS', value: '1' }
  { name: 'DOCUMENTS_CONTAINER_NAME', value: 'procurawise-documents' }
  { name: 'DOCUMENTS_MAX_FILE_SIZE_MB', value: '25' }
  { name: 'DOCUMENTS_DOWNLOAD_URL_TTL_MINUTES', value: '15' }
  { name: 'REPORTS_CONTAINER_NAME', value: 'procurawise-reports' }
  { name: 'REPORTS_DOWNLOAD_URL_TTL_MINUTES', value: '15' }
  { name: 'REPORTS_RETENTION_DAYS', value: '365' }
  { name: 'IMPORT_MAX_FILE_SIZE_MB', value: '10' }
  { name: 'NOTIFICATIONS_EMAIL_ENABLED', value: 'false' }
  { name: 'BILLING_ENABLED', value: 'false' }
  { name: 'STRIPE_REQUEST_TIMEOUT_SECONDS', value: '20' }
  { name: 'BILLING_WEBHOOK_EVENT_RETENTION_DAYS', value: '30' }
  { name: 'CORS_ALLOWED_ORIGINS', value: 'https://REPLACE_ME_FRONTEND_FQDN' }
  { name: 'RATE_LIMIT_LOGIN_MAX_ATTEMPTS', value: '5' }
  { name: 'RATE_LIMIT_LOGIN_WINDOW_SECONDS', value: '60' }
  { name: 'RATE_LIMIT_AI_MAX_REQUESTS', value: '10' }
  { name: 'RATE_LIMIT_AI_WINDOW_SECONDS', value: '3600' }
  { name: 'RATE_LIMIT_BILLING_CHECKOUT_MAX_REQUESTS', value: '5' }
  { name: 'RATE_LIMIT_BILLING_CHECKOUT_WINDOW_SECONDS', value: '3600' }
]
