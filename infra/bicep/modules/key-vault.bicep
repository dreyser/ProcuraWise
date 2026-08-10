// Fase 27 (ADR 0004/0019, deployment.md "Gestión de secretos"): Key Vault
// vacío - ningún valor de secreto se define aquí ni en ningún .bicepparam
// comiteado (CLAUDE.md §5/§8: "ningún secreto se hardcodea ni se comitea").
// Los nombres de secretos que Container Apps espera (ver
// modules/container-app.bicep) se poblan una sola vez, manualmente, por el
// founder durante el runbook de aprovisionamiento inicial
// (infra/scripts/bootstrap-oidc.md / deployment.md "Aprovisionamiento
// inicial"), vía `az keyvault secret set` o el portal - nunca por este
// template. RBAC-based access (no access policies clásicas) - más simple de
// auditar/asignar vía `Microsoft.Authorization/roleAssignments` en
// resources.bicep.

param location string
param name string
param tenantId string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
  }
}

output id string = vault.id
output uri string = vault.properties.vaultUri
output name string = vault.name
