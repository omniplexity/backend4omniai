#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building and pushing backend image..."
"${SCRIPT_DIR}/build-backend-image.sh"

echo "Applying Kubernetes manifests..."
"${SCRIPT_DIR}/../deploy/k8s/apply.sh"
