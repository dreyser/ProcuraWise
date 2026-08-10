// Fase 27: identidad administrada asignada por el usuario, una por
// Container App (api/worker) - RBAC mínimo necesario (AcrPull sobre el
// registry, Key Vault Secrets User sobre el vault) se otorga en
// resources.bicep, no aquí, porque requiere referencias a esos recursos ya
// creados en ese scope.

param location string
param name string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

output id string = identity.id
output principalId string = identity.properties.principalId
