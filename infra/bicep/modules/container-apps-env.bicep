// Fase 27 (ADR 0019): Container Apps Environment - la plataforma compartida
// sobre la que corren los Container Apps de api y worker (mismo Environment
// para ambos, igual que docker-compose.yml los corre en la misma red local
// hoy).

param location string
param name string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

output id string = environment.id
