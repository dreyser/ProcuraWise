// Fase 27 (deployment.md "Azure Blob Storage"): cuenta de almacenamiento +
// los 3 contenedores Blob que la app ya espera por nombre desde fases
// anteriores (genérico/health-check, `documents_container_name` Fase 16,
// `reports_container_name` Fase 23 - ver shared/config.py). El nombre
// exacto de cada contenedor lo fija el .bicepparam del ambiente para que
// coincida con el valor real configurado en Key Vault/env vars del
// Container App - este módulo no asume el valor por defecto de
// `shared/config.py` (ese default es solo válido para local).

param location string
param name string
param containerNames array
param sku string = 'Standard_LRS'

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  kind: 'StorageV2'
  sku: {
    name: sku
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in containerNames: {
    parent: blobService
    name: containerName
    properties: {
      publicAccess: 'None'
    }
  }
]

output id string = account.id
output name string = account.name
