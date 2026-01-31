#!/usr/bin/env bash
set -euo pipefail

if grep -q "REPLACE_ME" "deploy/k8s/secrets.yaml"; then
  echo "deploy/k8s/secrets.yaml still contains REPLACE_ME placeholders."
  echo "Update it or create the secret manually before applying manifests."
  exit 1
fi

files=(
  namespace.yaml
  configmap.yaml
  secrets.yaml
  pvc.yaml
  backend-deployment.yaml
  backend-service.yaml
  ngrok-deployment.yaml
)

for file in "${files[@]}"; do
  kubectl apply -f "deploy/k8s/$file"
done

kubectl rollout status deployment/omniai-backend -n omniai
