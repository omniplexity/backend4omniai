param(
  [string]$Namespace = "omniai"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$secretsPath = Join-Path $scriptDir "secrets.yaml"

if (Select-String -Path $secretsPath -Pattern "REPLACE_ME" -Quiet) {
  Write-Host "deploy/k8s/secrets.yaml still contains REPLACE_ME placeholders." -ForegroundColor Red
  Write-Host "Update it or create the secret manually before applying manifests."
  exit 1
}

$files = @(
  "namespace.yaml",
  "configmap.yaml",
  "secrets.yaml",
  "pvc.yaml",
  "backend-deployment.yaml",
  "backend-service.yaml",
  "ngrok-deployment.yaml"
)

foreach ($file in $files) {
  $path = Join-Path $scriptDir $file
  kubectl apply -f $path
}

kubectl rollout status deployment/omniai-backend -n $Namespace
