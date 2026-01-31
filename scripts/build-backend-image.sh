#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${REGISTRY_URL:-}" ]]; then
  echo "REGISTRY_URL must be provided (e.g., ghcr.io)"
  exit 1
fi

if [[ -z "${REGISTRY_REPOSITORY:-}" ]]; then
  echo "REGISTRY_REPOSITORY must be provided (e.g., omniplexity/omniai-backend)"
  exit 1
fi

if [[ -z "${REGISTRY_USERNAME:-}" ]]; then
  echo "REGISTRY_USERNAME must be provided"
  exit 1
fi

if [[ -z "${REGISTRY_PASSWORD:-}" ]]; then
  echo "REGISTRY_PASSWORD must be provided"
  exit 1
fi

TAG="${REGISTRY_TAG:-latest}"
IMAGE="${REGISTRY_URL}/${REGISTRY_REPOSITORY}:${TAG}"
ALT_IMAGE="${REGISTRY_URL}/${REGISTRY_REPOSITORY}:latest"

echo "Logging into ${REGISTRY_URL}"
echo "${REGISTRY_PASSWORD}" | docker login --username "${REGISTRY_USERNAME}" --password-stdin "${REGISTRY_URL}"

echo "Building ${IMAGE}"
docker build -t "${IMAGE}" backend

echo "Tagging ${ALT_IMAGE}"
docker tag "${IMAGE}" "${ALT_IMAGE}"

echo "Pushing ${IMAGE} and ${ALT_IMAGE}"
docker push "${IMAGE}"
docker push "${ALT_IMAGE}"
