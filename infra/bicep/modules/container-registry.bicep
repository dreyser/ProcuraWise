// Fase 27 (ADR 0004/0019): Azure Container Registry - imágenes de
// `Dockerfile.api`/`Dockerfile.worker` publicadas aquí por
// `deploy-staging.yml`/`deploy-prod.yml` vía OIDC federado, nunca con un
// usuario/contraseña de admin de larga vida (`adminUserEnabled: false`) -
// los Container Apps hacen pull con su propia identidad administrada
// (role assignment `AcrPull` en resources.bicep), y el pipeline hace push
// con la misma identidad federada que ejecuta el resto del deploy.

param location string
param name string
param sku string = 'Basic'

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: false
  }
}

output id string = registry.id
output loginServer string = registry.properties.loginServer
