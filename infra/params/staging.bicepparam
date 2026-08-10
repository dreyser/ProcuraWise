// Fase 27 - valores no-secretos para el ambiente staging. `apiImage`/
// `workerImage` se sobrescriben en cada corrida real de
// deploy-staging.yml con el tag recién publicado a ACR (`az deployment sub
// create ... --parameters apiImage=... workerImage=...`) - los valores aquí
// son solo un placeholder válido para que `az bicep build`/`what-if` no
// fallen por un parámetro requerido faltante.
//
// Ningún valor de este archivo es secreto (CLAUDE.md §5/§8) - los
// secretos reales viven únicamente en Key Vault, poblados manualmente
// durante el runbook de aprovisionamiento (deployment.md "Aprovisionamiento
// inicial (Fase 27)").

using '../bicep/main.bicep'

param environmentName = 'staging'
param location = 'eastus2'
param namePrefix = 'procurawise'

param apiImage = 'procurawiseacrstaging.azurecr.io/procurawise-api:placeholder'
param workerImage = 'procurawiseacrstaging.azurecr.io/procurawise-worker:placeholder'

param storageContainerNames = [
  'procurawise-staging'
  'procurawise-documents'
  'procurawise-reports'
]

// Mismo set de nombres de env var para api y worker (ambos instancian la
// misma clase Settings) - ver shared/config.py para el significado de cada
// uno. `ENVIRONMENT=staging` es lo que activa `is_production_like` (Fase
// 27, Pregunta bloqueante 1) sin forzar claves Stripe live.
param plainEnv = [
  { name: 'ENVIRONMENT', value: 'staging' }
  { name: 'LOG_LEVEL', value: 'info' }
  { name: 'MONGODB_DB_NAME', value: 'procurawise_staging' }
  { name: 'STORAGE_CONTAINER_NAME', value: 'procurawise-staging' }
  { name: 'AZURE_STORAGE_API_VERSION', value: '2025-01-05' }
  { name: 'QUEUE_BACKEND', value: 'service_bus' }
  { name: 'JWT_ALGORITHM', value: 'HS256' }
  { name: 'ACCESS_TOKEN_TTL_MINUTES', value: '30' }
  { name: 'PRE_SESSION_TOKEN_TTL_MINUTES', value: '5' }
  { name: 'OIDC_MICROSOFT_TENANT', value: 'common' }
  // Poblados por el founder tras registrar el App Registration OIDC de
  // Microsoft/Google (client id no es secreto, a diferencia del secret) -
  // placeholder aquí, corregido en el primer deploy real.
  { name: 'OIDC_MICROSOFT_CLIENT_ID', value: 'REPLACE_ME' }
  { name: 'OIDC_GOOGLE_CLIENT_ID', value: 'REPLACE_ME' }
  { name: 'OIDC_REDIRECT_BASE_URL', value: 'https://REPLACE_ME_API_FQDN' }
  { name: 'FRONTEND_BASE_URL', value: 'https://REPLACE_ME_FRONTEND_FQDN' }
  { name: 'AUDIT_EVENT_RETENTION_DAYS', value: '365' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: 'REPLACE_ME' }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: 'REPLACE_ME' }
  { name: 'AZURE_OPENAI_API_VERSION', value: '2026-01-01-preview' }
  { name: 'AI_REQUEST_TIMEOUT_SECONDS', value: '30' }
  { name: 'AI_EXECUTION_RETENTION_DAYS', value: '365' }
  { name: 'AI_SCORE_SUGGESTION_ENABLED', value: 'true' }
  { name: 'FOUNDRY_WEB_SEARCH_ENABLED', value: 'false' }
  { name: 'VENDOR_INVITATION_TTL_DAYS', value: '7' }
  // Container Apps es un único hop de reverse-proxy real frente a la API -
  // re-verificado en el primer deploy real (comentario de Fase 27 en
  // shared/config.py sobre trusted_proxy_hops), no asumido sin evidencia.
  { name: 'TRUSTED_PROXY_HOPS', value: '1' }
  { name: 'DOCUMENTS_CONTAINER_NAME', value: 'procurawise-documents' }
  { name: 'DOCUMENTS_MAX_FILE_SIZE_MB', value: '25' }
  { name: 'DOCUMENTS_DOWNLOAD_URL_TTL_MINUTES', value: '15' }
  { name: 'REPORTS_CONTAINER_NAME', value: 'procurawise-reports' }
  { name: 'REPORTS_DOWNLOAD_URL_TTL_MINUTES', value: '15' }
  { name: 'REPORTS_RETENTION_DAYS', value: '365' }
  { name: 'IMPORT_MAX_FILE_SIZE_MB', value: '10' }
  // Apagados por defecto incluso en staging - se activan explícitamente
  // (junto con las credenciales reales correspondientes en Key Vault)
  // cuando el founder quiera ejercitar esos flujos en staging.
  { name: 'NOTIFICATIONS_EMAIL_ENABLED', value: 'false' }
  { name: 'BILLING_ENABLED', value: 'false' }
  { name: 'STRIPE_REQUEST_TIMEOUT_SECONDS', value: '20' }
  { name: 'BILLING_WEBHOOK_EVENT_RETENTION_DAYS', value: '30' }
  // CORS: mismo dominio de la SPA de staging únicamente, nunca vacío en
  // Azure real (deny-all por defecto solo tiene sentido cuando no hay SPA
  // real que llamar - Fase 26).
  { name: 'CORS_ALLOWED_ORIGINS', value: 'https://REPLACE_ME_FRONTEND_FQDN' }
  { name: 'RATE_LIMIT_LOGIN_MAX_ATTEMPTS', value: '5' }
  { name: 'RATE_LIMIT_LOGIN_WINDOW_SECONDS', value: '60' }
  { name: 'RATE_LIMIT_AI_MAX_REQUESTS', value: '10' }
  { name: 'RATE_LIMIT_AI_WINDOW_SECONDS', value: '3600' }
  { name: 'RATE_LIMIT_BILLING_CHECKOUT_MAX_REQUESTS', value: '5' }
  { name: 'RATE_LIMIT_BILLING_CHECKOUT_WINDOW_SECONDS', value: '3600' }
]
