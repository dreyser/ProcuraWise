// Fase 27 (ADR 0019): módulo genérico de Container App, reusado para api y
// worker (resources.bicep los instancia dos veces con params distintos) -
// ambos comparten la misma imagen base/paquete `procurawise` (monolito
// modular, CLAUDE.md §3) y la misma forma de Container App; solo difieren
// en ingress/probes (la API expone HTTP, el worker es un loop de consumo
// de cola sin superficie de red - ver Dockerfile.worker) y en la imagen que
// corren. Pull de ACR e inyección de secretos desde Key Vault vía la misma
// identidad administrada asignada por el usuario (sin usuario/contraseña de
// admin de ACR, sin secretos horneados - deployment.md "Gestión de
// secretos").

param location string
param name string
param containerAppsEnvironmentId string
param userAssignedIdentityId string
param acrLoginServer string
param image string
param hasIngress bool
param targetPort int = 8000
// Fase 28: parametrizado para reusar este módulo también para el frontend
// estático (nginx, sin `/health/live`/`/health/ready` propios de la API -
// ver Dockerfile.web) - default sin cambios para api/worker.
param livenessPath string = '/health/live'
param readinessPath string = '/health/ready'
// Fija en 1 réplica por defecto - deliberado, no un olvido. shared/rate_limit.py
// (Fase 26) es in-process y no coordina su conteo entre réplicas; el
// threat-model.md documenta ese gap como "irrelevante mientras Container
// Apps corra una sola réplica". Subir maxReplicas es una decisión explícita
// a tomar junto con esa limitación (coordinar el rate limiter, p. ej. vía
// un backend compartido), no un valor a subir sin más porque Container Apps
// lo permite.
param minReplicas int = 1
param maxReplicas int = 1
param cpu string = '0.5'
param memory string = '1Gi'

@description('Secretos referenciados desde Key Vault - {envName, secretName, keyVaultUrl}. `secretName` (minúsculas-con-guiones, restricción de Container Apps/Key Vault) es distinto de `envName` (MAYUSCULAS_CON_GUION_BAJO, el nombre que pydantic-settings espera - p. ej. secretName="jwt-secret", envName="JWT_SECRET"). Los valores reales se poblaron manualmente en Key Vault durante el runbook de aprovisionamiento (nunca en este template/.bicepparam).')
param keyVaultSecrets array = []

@description('Variables de entorno no-secretas, específicas del ambiente (staging/production) - ver infra/params/*.bicepparam.')
param plainEnv array = []

var secretEnvRefs = [
  for secret in keyVaultSecrets: {
    name: secret.envName
    secretRef: secret.secretName
  }
]

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          identity: userAssignedIdentityId
        }
      ]
      secrets: [
        for secret in keyVaultSecrets: {
          name: secret.secretName
          keyVaultUrl: secret.keyVaultUrl
          identity: userAssignedIdentityId
        }
      ]
      ingress: hasIngress
        ? {
            external: true
            targetPort: targetPort
            transport: 'auto'
            allowInsecure: false
          }
        : null
    }
    template: {
      containers: [
        {
          name: name
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: union(plainEnv, secretEnvRefs)
          probes: hasIngress
            ? [
                {
                  type: 'Liveness'
                  httpGet: {
                    path: livenessPath
                    port: targetPort
                  }
                  initialDelaySeconds: 5
                  periodSeconds: 15
                }
                {
                  type: 'Readiness'
                  httpGet: {
                    path: readinessPath
                    port: targetPort
                  }
                  initialDelaySeconds: 5
                  periodSeconds: 15
                }
              ]
            : []
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output id string = containerApp.id
output fqdn string = hasIngress ? containerApp.properties.configuration.ingress.fqdn : ''
