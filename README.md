# OmniAI Platform

This repository coordinates the backend runtime, deployment tooling, and Kubernetes manifests that keep the service always available. The UI lives in a separate repository; this repo focuses on backend + cluster operations.

- **Backend**: `https://github.com/omniplexity/backend4omniai` contains the FastAPI server, authentication, and database logic. The same code is shipped as a Docker image (`ghcr.io/omniplexity/omniai-backend:latest`) and consumed by the Kubernetes cluster described below.
- **Frontend**: `https://github.com/omniplexity/omniplexity.github.io` hosts the single-page UI built and published via GitHub Pages. Its runtime config must point at the cluster’s public endpoint (ngrok domain).

## Always-up Kubernetes cluster

Everything that exposes or serves the platform lives inside the `deploy/k8s` namespace:

- `deploy/k8s/backend-deployment.yaml` runs the FastAPI server (single replica + SQLite PVC) and exposes it via `deploy/k8s/backend-service.yaml`.  
- `deploy/k8s/ngrok-deployment.yaml` recreates the ngrok tunnel, keeping the HTTP API reachable from the public Internet.
- Configuration, secrets, and persistence happen through the ConfigMap, Secret manifest, and `omiai-sqlite-pvc`.  
- `deploy/k8s/secrets.yaml` is a template. Replace every `REPLACE_ME` (or create the secret manually) before applying.  
- Run `deploy/k8s/apply.sh` (or `deploy/k8s/apply.ps1` on Windows) after updating config/secrets to apply everything in order; the script waits for the backend rollout so you can detect failures early.

## CI/CD and deployment flow

1. The backend repo already includes `backend/.github/workflows/ci.yml`, which installs deps, runs `pytest`, and builds/pushes the Docker image. You can either:
   - Provide `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`, and `REGISTRY_REPOSITORY` via the repository secrets/settings so a push to `main` can run automatically, **or**
   - Trigger the workflow manually (`Actions → Backend CI & Deploy → Run workflow`) and pass those values as inputs to the workflow helper since it now accepts them at runtime.
   The workflow fails fast if any of the three values are still missing, so make sure the runner environment (self-hosted agent, CI orchestrator, or manual dispatch dialog) provides them.
2. Instead of doing the build/push/apply sequence by hand, run `scripts/deploy-stack.sh` after exporting:
   ```bash
   export REGISTRY_URL=ghcr.io
   export REGISTRY_REPOSITORY=omniplexity/omniai-backend
   export REGISTRY_USERNAME=<username>
   export REGISTRY_PASSWORD=<password>
   export REGISTRY_TAG=v1.0.0  # optional, defaults to latest
   ./scripts/deploy-stack.sh
   ```
   The script builds/pushes the backend image (via `scripts/build-backend-image.sh`) and then applies the Kubernetes manifests through `deploy/k8s/apply.sh`, so you no longer need to manually run those commands in sequence.
   - `REGISTRY_USERNAME`
   - `REGISTRY_PASSWORD`
   - `REGISTRY_REPOSITORY` (e.g., `omniplexity/omniai-backend`)
2. After the image lands in the registry, update `deploy/k8s/backend-deployment.yaml` if it should track a different tag or namespace (it currently points at `ghcr.io/omniplexity/omniai-backend:latest`).
3. Apply the manifests (`deploy/k8s/apply.sh`) on your target cluster. The namespace, ConfigMap, Secret, PVC, backend, and ngrok resources are versioned together so the entire stack is redeployed atomically.
4. The frontend repo should rebuild whenever the API URL or domain changes—update its `runtime-config.json` or any env-driven config before publishing to GitHub Pages. Make sure CORS origins and tunnel domains in the ConfigMap align with what the frontend expects.

## Secrets and local provider access

- Do not store real secrets in version control. Replace placeholders in `deploy/k8s/secrets.yaml` or create the secret with `kubectl create secret`.
- If you are running LM Studio or Ollama locally on the host, the K8s ConfigMap uses `host.docker.internal` so pods can reach the host services from Docker Desktop.
- Windows helper: `scripts/create-k8s-secrets.ps1` creates `omniai-backend-secrets` from environment variables.

## Monitoring & resilience

- Kubernetes ensures the pods restart automatically on failure (`Deployment` + readiness/liveness probes). The PVC keeps SQLite data persistent, while the ngrok tunnel keeps the API reachable.
- Use `kubectl rollout status` and the apply helper to confirm the backend is healthy. If the API needs to scale beyond SQLite limits, switch the ConfigMap to a PostgreSQL URL in `DATABASE_URL` and replicate the PVC logic with a proper `PersistentVolume`.

If you need help wiring GitHub Actions, updating the frontend runtime config, or automating cluster rollout (ArgoCD, Flux, etc.), let me know and I can add the necessary manifests.
