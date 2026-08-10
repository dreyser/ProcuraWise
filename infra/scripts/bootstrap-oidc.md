# Aprovisionamiento inicial de Fase 27 — runbook manual

Ejecutado **una sola vez por ambiente** (`staging`, luego `production` cuando aplique) por el founder, con sus propias credenciales de Azure (rol `Owner`/`Contributor` a nivel de suscripción o al menos `Microsoft.Authorization/roleAssignments/write` + `Microsoft.Resources/resourceGroups/write`). Ningún paso de este documento es re-ejecutable idempotentemente desde `deploy-staging.yml`/`deploy-prod.yml` — el pipeline recurrente corre con una identidad federada (OIDC) que deliberadamente **no** tiene permiso para crear resource groups ni asignar roles (plan Fase 27 §14, mínimo privilegio); solo para desplegar dentro de un resource group que ya existe.

No se ejecuta nada de este runbook automáticamente en ninguna sesión de Claude Code — son comandos `az` que el founder corre en su propia terminal, con su propia sesión `az login`.

## 1. Crear el resource group (una vez por ambiente)

```bash
az group create --name rg-procurawise-staging --location eastus2
```

(Repetir con `rg-procurawise-production` cuando se aprovisione producción.)

## 2. Registrar la App Registration + Service Principal para OIDC federado

```bash
az ad app create --display-name "procurawise-deploy-staging" \
  --query appId -o tsv > /tmp/procurawise-staging-app-id.txt

APP_ID=$(cat /tmp/procurawise-staging-app-id.txt)
az ad sp create --id "$APP_ID"
```

Repetir con un segundo App Registration (`procurawise-deploy-production`) para producción — **identidades separadas por ambiente**, no una sola compartida, para que un compromiso de la identidad de staging nunca alcance producción.

## 3. Federated credential (sin secretos de larga vida)

```bash
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-actions-staging",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<org>/<repo>:environment:staging",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

El `subject` usa `environment:staging` (no `ref:refs/heads/main`) porque `deploy-staging.yml` declara `environment: staging` — esto ata la credencial federada al *GitHub Environment*, no a una rama, para que las reglas de protección del Environment (si se configuran más adelante) también gateen quién puede obtener el token OIDC. Para producción, usar `"subject": "repo:<org>/<repo>:environment:production"` contra el segundo App Registration.

## 4. Rol `Contributor` acotado al resource group (nunca a la suscripción)

```bash
SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-procurawise-staging"
```

## 5. Secrets del repositorio (GitHub → Settings → Secrets and variables → Actions)

Ninguno de estos valores es un secreto de larga vida — son identificadores públicos que habilitan el intercambio de token OIDC en cada corrida, no una credencial estática:

| Secret | Valor |
|---|---|
| `AZURE_CLIENT_ID` (staging) | `$APP_ID` del paso 2 |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |
| `AZURE_CLIENT_ID_PROD` (producción) | App id del segundo App Registration |

## 6. Poblar Key Vault con los secretos reales

`main.bicep` crea las 8 entradas de Key Vault que requieren un valor real externo (ver el comentario `founderPopulatedSecretNames`) con un valor placeholder de un solo espacio — el primer `az deployment group create` real las deja así, y el arranque de la app fallará limpiamente (mensaje de validación de `shared/config.py`, no un traceback opaco) hasta que se completen aquí:

```bash
KV_NAME="procurawise-kv-staging"

az keyvault secret set --vault-name "$KV_NAME" --name mongodb-uri --value "mongodb+srv://<user>:<password>@<cluster>.mongodb.net/procurawise_staging?retryWrites=true&w=majority"
az keyvault secret set --vault-name "$KV_NAME" --name jwt-secret --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name "$KV_NAME" --name oidc-microsoft-client-secret --value "<del App Registration de login Microsoft>"
az keyvault secret set --vault-name "$KV_NAME" --name oidc-google-client-secret --value "<de Google Cloud Console>"
az keyvault secret set --vault-name "$KV_NAME" --name azure-openai-api-key --value "<clave del recurso Azure OpenAI>"
# acs-connection-string / stripe-secret-key / stripe-webhook-secret solo son
# requeridos si NOTIFICATIONS_EMAIL_ENABLED/BILLING_ENABLED se activan en
# infra/params/staging.bicepparam (ambos "false" por defecto en esta fase) -
# poblar solo cuando se decida activar esos flujos en staging.
```

`storage-connection-string`/`service-bus-connection-string` **no** se tocan aquí — `main.bicep` los genera automáticamente a partir de los recursos que el mismo template crea (Bicep ya conoce esos valores, no hay razón para pedírselos al founder).

`plainEnv` en `infra/params/staging.bicepparam` tiene varios valores `REPLACE_ME` (client id de OIDC, endpoint/deployment de Azure OpenAI, FQDN del frontend) — reemplazarlos con los valores reales antes o durante el primer deploy (vía `--parameters` en la línea de comandos de `az deployment group create`, sin necesidad de comitear el `.bicepparam` con esos valores si se prefiere pasarlos solo en ese momento).

## 7. Primer deploy real (verificación del criterio de aceptación de Fase 27)

```bash
az deployment group create \
  --resource-group rg-procurawise-staging \
  --template-file infra/bicep/main.bicep \
  --parameters infra/params/staging.bicepparam \
  --parameters apiImage=<acr-login-server>/procurawise-api:bootstrap workerImage=<acr-login-server>/procurawise-worker:bootstrap
```

(La primera corrida necesita una imagen ya publicada en ACR - puede ser un build local (`docker build` + `az acr login` + `docker push`) antes de que exista el pipeline, o simplemente disparar `deploy-staging.yml` manualmente vía `workflow_dispatch` una vez los secrets del paso 5 estén configurados.)

Tras el deploy: `curl https://<apiFqdn output>/health/ready` debe responder `200` con `mongodb`/`storage` en `true` (Atlas real y Storage Account real, no más Docker local) — esto es lo que finalmente confirma el criterio de aceptación textual de Fase 27 ("Deploy a staging exitoso vía pipeline, sin secretos de larga vida en el repo"). Registrar el resultado (fecha, `apiFqdn`, respuesta de `/health/ready`) en `docs/development/current-phase.md`, mismo mecanismo ya usado para las demos manuales de Fases 15/25.

**Último paso, después de confirmar el primer deploy exitoso**: `deploy-staging.yml` corre solo manualmente (`workflow_dispatch`) hasta este punto — sin el trigger `push: branches: [main]`, deliberadamente comentado, para que no falle en rojo en cada merge a `main` mientras los secrets del paso 5 no existen. Una vez confirmado el primer deploy real, descomentar ese trigger en `.github/workflows/deploy-staging.yml` (PR normal, mismo flujo que cualquier otro cambio) para volver al despliegue continuo automático a staging en cada merge.

## MongoDB Atlas (fuera de Bicep — plan §11, decisión recomendada #1)

Atlas no es un recurso Azure; Bicep no puede aprovisionarlo. Crear manualmente en <https://cloud.mongodb.com>:

1. Organización/proyecto "ProcuraWise" (si no existe ya).
2. Cluster M0 (mismo tier que ADR 0015 aprobó para todo el MVP — no reabrir esa decisión aquí).
3. IP access list: agregar el rango de salida de Azure Container Apps para la región elegida (o `0.0.0.0/0` temporalmente solo para el primer smoke test, nunca en producción — Atlas M0 no soporta Private Endpoint, riesgo ya aceptado explícitamente en ADR 0015/`threat-model.md`).
4. Usuario de base de datos dedicado (`procurawise-staging`), contraseña generada aleatoriamente — el connection string resultante es el valor de `mongodb-uri` del paso 6.
