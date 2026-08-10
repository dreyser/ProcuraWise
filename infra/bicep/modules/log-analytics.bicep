// Fase 27 (ADR 0004/0019): Log Analytics workspace backing the Container
// Apps Environment's built-in logging - no separate Application Insights
// resource in this phase (not requested by the backlog criterion, candidate
// for a later observability pass if needed).

param location string
param name string
param retentionInDays int = 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
  }
}

output id string = workspace.id
output customerId string = workspace.properties.customerId
@secure()
output primarySharedKey string = workspace.listKeys().primarySharedKey
