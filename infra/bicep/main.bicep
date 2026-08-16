// Fase 27 (ADR 0004/0005/0015/0019): punto de entrada, scope de resource
// group - desplegado vía `az deployment group create --resource-group
// rg-procurawise-{env} --template-file main.bicep --parameters
// params/{env}.bicepparam` (deploy-staging.yml/deploy-prod.yml). El
// resource group en sí NO lo crea este template: se crea una única vez,
// manualmente, durante el bootstrap (infra/scripts/bootstrap-oidc.md) -
// deliberado, no un descuido: la identidad federada OIDC que ejecuta el
// pipeline solo recibe el rol `Contributor` acotado a ese resource group
// (plan §14, mínimo privilegio), y "crear un resource group" es en sí una
// operación de scope de suscripción que esa identidad no tiene permiso de
// hacer - manteniendo el pipeline recurrente limpio de cualquier permiso
// más amplio que el estrictamente necesario para desplegar dentro de un
// resource group que ya existe.
//
// Compone todos los recursos de deployment.md salvo MongoDB Atlas (no es
// un recurso Azure, Bicep no puede aprovisionarlo - plan §11, decisión
// recomendada #1; documentado como runbook manual en
// infra/scripts/bootstrap-oidc.md/deployment.md) y el recurso cognitivo de
// Azure OpenAI/ACS en sí (ya tratados como servicios externos configurados
// vía Key Vault - candidato a una fase posterior si el founder pide
// aprovisionarlos también desde este template).

param location string = 'eastus2'
param environmentName string
param namePrefix string = 'procurawise'
param tenantId string = subscription().tenantId

@description('Imagen completa (con tag) publicada en ACR por el paso de build del workflow - p. ej. "procurawiseacr.azurecr.io/procurawise-api:sha-abc123".')
param apiImage string
param workerImage string
// Fase 28 (ADR 0019, nota de alcance): tercer Container App, sirve el
// build estático del SPA (nginx, sin backend propio - ver Dockerfile.web).
param webImage string

@description('Nombres de contenedores Blob a crear - ver shared/config.py (storage_container_name/documents_container_name/reports_container_name).')
param storageContainerNames array

@description('Variables de entorno no-secretas para api y worker (ambos comparten la misma clase Settings, así que ambos necesitan el mismo set) - ver infra/params/*.bicepparam.')
param plainEnv array

var acrName = replace('${namePrefix}acr${environmentName}', '-', '')
var keyVaultName = '${namePrefix}-kv-${environmentName}'
var logAnalyticsName = '${namePrefix}-log-${environmentName}'
var containerAppsEnvName = '${namePrefix}-cae-${environmentName}'
var storageAccountName = replace('${namePrefix}st${environmentName}', '-', '')
var serviceBusName = '${namePrefix}-sb-${environmentName}'
var apiIdentityName = '${namePrefix}-id-api-${environmentName}'
var workerIdentityName = '${namePrefix}-id-worker-${environmentName}'
var webIdentityName = '${namePrefix}-id-web-${environmentName}'
var apiAppName = '${namePrefix}-api-${environmentName}'
var workerAppName = '${namePrefix}-worker-${environmentName}'
var webAppName = '${namePrefix}-web-${environmentName}'

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  params: {
    location: location
    name: logAnalyticsName
  }
}

module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    location: location
    name: acrName
  }
}

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    location: location
    name: keyVaultName
    tenantId: tenantId
  }
}

module containerAppsEnvironment 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  params: {
    location: location
    name: containerAppsEnvName
    logAnalyticsCustomerId: logAnalytics.outputs.customerId
    logAnalyticsSharedKey: logAnalytics.outputs.primarySharedKey
  }
}

module storageAccount 'modules/storage-account.bicep' = {
  name: 'storage-account'
  params: {
    location: location
    name: storageAccountName
    containerNames: storageContainerNames
  }
}

module serviceBus 'modules/service-bus.bicep' = {
  name: 'service-bus'
  params: {
    location: location
    name: serviceBusName
  }
}

module apiIdentity 'modules/managed-identity.bicep' = {
  name: 'api-identity'
  params: {
    location: location
    name: apiIdentityName
  }
}

module workerIdentity 'modules/managed-identity.bicep' = {
  name: 'worker-identity'
  params: {
    location: location
    name: workerIdentityName
  }
}

module webIdentity 'modules/managed-identity.bicep' = {
  name: 'web-identity'
  params: {
    location: location
    name: webIdentityName
  }
}

// RBAC mínimo: AcrPull (pull de imágenes) + Key Vault Secrets User (leer
// valores de secretos referenciados) para cada identidad - nunca
// Contributor/Owner sobre estos recursos (CLAUDE.md §4, mínimo privilegio
// aplicado a infraestructura en vez de a un endpoint de negocio, plan §14).
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var keyVaultSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource acrRef 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
  dependsOn: [containerRegistry]
}

resource keyVaultRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
  dependsOn: [keyVault]
}

resource apiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, apiIdentityName, acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: apiIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

resource workerAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, workerIdentityName, acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: workerIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// Fase 28: el frontend no lee ningún secreto de Key Vault en runtime
// (VITE_API_BASE_URL se hornea en build - Dockerfile.web) - solo necesita
// AcrPull para bajar su propia imagen, nunca Key Vault Secrets User.
resource webAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, webIdentityName, acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: webIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apiKvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultRef.id, apiIdentityName, keyVaultSecretsUserRoleId)
  scope: keyVaultRef
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: apiIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

resource workerKvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultRef.id, workerIdentityName, keyVaultSecretsUserRoleId)
  scope: keyVaultRef
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: workerIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// Secretos auto-generados por recursos que este mismo template ya crea
// (Bicep conoce su valor real - no hay razón para pedírselo al founder).
resource storageConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVaultRef
  name: 'storage-connection-string'
  properties: {
    value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.outputs.name};AccountKey=${listKeys(resourceId('Microsoft.Storage/storageAccounts', storageAccountName), '2023-05-01').keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
  }
}

resource serviceBusConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVaultRef
  name: 'service-bus-connection-string'
  properties: {
    value: serviceBus.outputs.connectionString
  }
}

// Secretos que solo el founder puede poblar (credenciales externas: Atlas,
// OIDC, Azure OpenAI, ACS, Stripe - deployment.md "Aprovisionamiento
// inicial"): mongodb-uri, jwt-secret, oidc-microsoft-client-secret,
// oidc-google-client-secret, azure-openai-api-key, acs-connection-string,
// stripe-secret-key, stripe-webhook-secret. Este template NUNCA los crea ni
// les escribe un valor - ni siquiera un placeholder - por el mismo motivo de
// mínimo privilegio que ya justifica que el resource group tampoco lo cree
// este template (comentario de arriba): la identidad recurrente del pipeline
// no tiene, ni necesita, permiso de escritura sobre datos de Key Vault.
// Se pueblan una sola vez, manualmente, vía infra/scripts/bootstrap-oidc.md
// (mismo principio que ya documenta modules/key-vault.bicep), ANTES del
// primer `az deployment group create` completo, porque el bloque `secrets:`
// de Container Apps (modules/container-app.bicep) resuelve cada
// `keyVaultUrl` al crear la revisión y falla si el nombre no existe todavía.
// (Corregido: una versión anterior de este archivo sí los creaba aquí con un
// valor placeholder de un solo espacio, sin condición - un redeploy
// ordinario pisaba el valor real que el founder ya había poblado.)

var commonKeyVaultSecrets = [
  { envName: 'MONGODB_URI', secretName: 'mongodb-uri', keyVaultUrl: '${keyVault.outputs.uri}secrets/mongodb-uri' }
  { envName: 'STORAGE_CONNECTION_STRING', secretName: 'storage-connection-string', keyVaultUrl: '${keyVault.outputs.uri}secrets/storage-connection-string' }
  { envName: 'SERVICE_BUS_CONNECTION_STRING', secretName: 'service-bus-connection-string', keyVaultUrl: '${keyVault.outputs.uri}secrets/service-bus-connection-string' }
  { envName: 'JWT_SECRET', secretName: 'jwt-secret', keyVaultUrl: '${keyVault.outputs.uri}secrets/jwt-secret' }
  { envName: 'OIDC_MICROSOFT_CLIENT_SECRET', secretName: 'oidc-microsoft-client-secret', keyVaultUrl: '${keyVault.outputs.uri}secrets/oidc-microsoft-client-secret' }
  { envName: 'OIDC_GOOGLE_CLIENT_SECRET', secretName: 'oidc-google-client-secret', keyVaultUrl: '${keyVault.outputs.uri}secrets/oidc-google-client-secret' }
  { envName: 'AZURE_OPENAI_API_KEY', secretName: 'azure-openai-api-key', keyVaultUrl: '${keyVault.outputs.uri}secrets/azure-openai-api-key' }
  { envName: 'ACS_CONNECTION_STRING', secretName: 'acs-connection-string', keyVaultUrl: '${keyVault.outputs.uri}secrets/acs-connection-string' }
  { envName: 'STRIPE_SECRET_KEY', secretName: 'stripe-secret-key', keyVaultUrl: '${keyVault.outputs.uri}secrets/stripe-secret-key' }
  { envName: 'STRIPE_WEBHOOK_SECRET', secretName: 'stripe-webhook-secret', keyVaultUrl: '${keyVault.outputs.uri}secrets/stripe-webhook-secret' }
]

module apiApp 'modules/container-app.bicep' = {
  name: 'api-app'
  params: {
    location: location
    name: apiAppName
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.id
    userAssignedIdentityId: apiIdentity.outputs.id
    acrLoginServer: containerRegistry.outputs.loginServer
    image: apiImage
    hasIngress: true
    targetPort: 8000
    keyVaultSecrets: commonKeyVaultSecrets
    plainEnv: plainEnv
  }
  dependsOn: [apiAcrPull, apiKvSecretsUser, storageConnectionStringSecret, serviceBusConnectionStringSecret]
}

module workerApp 'modules/container-app.bicep' = {
  name: 'worker-app'
  params: {
    location: location
    name: workerAppName
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.id
    userAssignedIdentityId: workerIdentity.outputs.id
    acrLoginServer: containerRegistry.outputs.loginServer
    image: workerImage
    hasIngress: false
    keyVaultSecrets: commonKeyVaultSecrets
    plainEnv: plainEnv
  }
  dependsOn: [workerAcrPull, workerKvSecretsUser, storageConnectionStringSecret, serviceBusConnectionStringSecret]
}

// Fase 28 (ADR 0019, nota de alcance): reusa el mismo módulo genérico de
// api/worker - sin Key Vault secrets, sin plainEnv (SPA estática, toda su
// config va horneada en el build de la imagen, no en runtime), probes
// apuntando a `/` en vez de `/health/*` (nginx no tiene esos paths - ver
// modules/container-app.bicep).
module webApp 'modules/container-app.bicep' = {
  name: 'web-app'
  params: {
    location: location
    name: webAppName
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.id
    userAssignedIdentityId: webIdentity.outputs.id
    acrLoginServer: containerRegistry.outputs.loginServer
    image: webImage
    hasIngress: true
    targetPort: 80
    livenessPath: '/'
    readinessPath: '/'
  }
  dependsOn: [webAcrPull]
}

output apiFqdn string = apiApp.outputs.fqdn
output webFqdn string = webApp.outputs.fqdn
output keyVaultName string = keyVault.outputs.name
output acrLoginServer string = containerRegistry.outputs.loginServer
