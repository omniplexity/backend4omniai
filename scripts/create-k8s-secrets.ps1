param(
  [string]$Namespace = "omniai"
)

$required = @(
  "SECRET_KEY",
  "OPENAI_COMPAT_API_KEY",
  "NGROK_AUTHTOKEN"
)

$missing = @()
foreach ($name in $required) {
  if ([string]::IsNullOrWhiteSpace($env:$name)) {
    $missing += $name
  }
}

if ($missing.Count -gt 0) {
  Write-Host "Missing required environment variables:" -ForegroundColor Red
  $missing | ForEach-Object { Write-Host " - $_" }
  exit 1
}

kubectl get ns $Namespace *> $null
if ($LASTEXITCODE -ne 0) {
  kubectl create namespace $Namespace | Out-Null
}

kubectl create secret generic omniai-backend-secrets `
  --namespace $Namespace `
  --from-literal=SECRET_KEY=$env:SECRET_KEY `
  --from-literal=OPENAI_COMPAT_API_KEY=$env:OPENAI_COMPAT_API_KEY `
  --from-literal=NGROK_AUTHTOKEN=$env:NGROK_AUTHTOKEN `
  --dry-run=client -o yaml | kubectl apply -f -
