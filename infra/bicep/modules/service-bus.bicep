// Fase 27 (ADR 0005/0020/0021): namespace Standard (plan §11, decisión
// recomendada #3 - NFR-003 no justifica Premium) + las 4 colas reales que
// `queue_backend=service_bus` despacha hoy (ver `JOB_TOPIC`/
// `SCORE_SUGGESTION_JOB_TOPIC` en ai/service.py, notifications/service.py,
// reports/service.py) - más que las 2 que
// `docker/servicebus-emulator/config.json` define (ese archivo quedó
// desactualizado desde las Fases 23/24, que agregaron report-generation/
// notification-email sin tocar la config del emulador local - un gap
// preexistente fuera del alcance de esta fase, ya que
// `queue_backend=memory` es el default local y el perfil `servicebus` es
// opcional). Contra Azure real (staging/producción) las 4 colas son
// obligatorias, no opcionales.

param location string
param name string
param sku string = 'Standard'

@description('Nombres de las 4 colas reales que el worker despacha - ai/service.py, notifications/service.py, reports/service.py.')
param queueNames array = [
  'ai-requirement-generation'
  'ai-score-suggestion'
  'notification-email'
  'report-generation'
]

resource namespace 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: name
  location: location
  sku: {
    name: sku
    tier: sku
  }
}

resource queues 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = [
  for queueName in queueNames: {
    parent: namespace
    name: queueName
    properties: {
      lockDuration: 'PT1M'
      defaultMessageTimeToLive: 'PT1H'
      maxDeliveryCount: 3
      requiresDuplicateDetection: false
      deadLetteringOnMessageExpiration: false
    }
  }
]

resource sendListenRule 'Microsoft.ServiceBus/namespaces/AuthorizationRules@2024-01-01' = {
  parent: namespace
  name: 'procurawise-app'
  properties: {
    rights: [
      'Send'
      'Listen'
    ]
  }
}

output id string = namespace.id
output name string = namespace.name
@secure()
output connectionString string = sendListenRule.listKeys().primaryConnectionString
