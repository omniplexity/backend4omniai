# Deploying OmniAI to Kubernetes

These manifests move the entire backend stack (SQLite persistence, FastAPI service, and ngrok tunnel) into a single Kubernetes namespace so every server component is managed by the cluster.

## What runs in the cluster

- `omni-backend`: The FastAPI service, pinned to one replica because it relies on a single SQLite file stored on a PVC.
- `ngrok`: Recreates the tunnel from `ngrok/ngrok` that exposes the backend to the public domain you provision.

## Steps

1. **Build and push the backend image**  
   ```bash
   docker build -t <registry>/omniai-backend:latest backend
   docker push <registry>/omniai-backend:latest
   ```
   Update `deploy/k8s/backend-deployment.yaml` to point at the image you pushed (replace `omniplexity/omniai-backend:latest`).
   The workflow at `backend/.github/workflows/ci.yml` already performs this build/push for pushes to `main`; update its secrets (`REGISTRY_USERNAME`, `REGISTRY_PASSWORD`, `REGISTRY_REPOSITORY`) to match your container registry if you rely on automated pushes.

2. **Adjust secrets**  
   `deploy/k8s/secrets.yaml` is a template. Replace every `REPLACE_ME` (or create the secret manually) before applying the manifests. Required keys:
   - `NGROK_AUTHTOKEN`
   - `SECRET_KEY`
   - `OPENAI_COMPAT_API_KEY`

   Example (manual secret creation):
   ```bash
   kubectl create secret generic omniai-backend-secrets \
     --namespace omniai \
     --from-literal=SECRET_KEY=... \
     --from-literal=OPENAI_COMPAT_API_KEY=... \
     --from-literal=NGROK_AUTHTOKEN=... \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
   Windows helper: `scripts/create-k8s-secrets.ps1`.

3. **Apply the namespace and resources**  
   Prefer using the helper script from `scripts/deploy-stack.sh` (which already builds/pushes the backend image) rather than typing every `kubectl apply` command manually. On Windows, use `deploy/k8s/apply.ps1`.

- **Accessing the backend**  
  - `kubectl port-forward -n omniai svc/omniai-backend 8000:8000` to reach the API locally.  
  - Once ngrok is healthy it will publish the backend to the domain you configured (`NGROK_DOMAIN`).

## CI/CD integrations

- **Backend automation**: `backend/.github/workflows/ci.yml` runs tests, then builds and pushes `ghcr.io/omniplexity/omniai-backend:latest` (or whatever `REGISTRY_REPOSITORY` you set) whenever you push to `main` or trigger it manually. You can feed the registry credentials either through repo secrets or by providing them as inputs to the manually dispatched workflow whenever you need to rebuild the image.
- **Deploy helper**: `deploy/k8s/apply.sh` (or `deploy/k8s/apply.ps1` on Windows) applies every manifest in order and waits for the backend rollout. Run it after secrets/config changes (or wire it into your CD tooling).
- **Frontend publishing**: The static UI lives in `https://github.com/omniplexity/omniplexity.github.io` and should be built/published to GitHub Pages as usual. Update its `runtime-config.json` (and any other runtime constants) to point at the cluster’s public domain so the SPA can talk to the new backend tunnels.

## Notes

- The SQLite database lives on `omiai-sqlite-pvc`. Adjust the PVC definition if you need a larger disk or a specific storage class.
- An init container runs `alembic upgrade head` before the backend pod starts to ensure the schema is present.
- `ConfigMap` entries mirror the `.env` defaults; edit them to match staging/production settings (CORS origins, provider hosts, etc.).
- Only one backend replica is supported because SQLite disallows concurrent writers on separate nodes. If you need high availability, switch to PostgreSQL (see `app/db/engine.py`).

If you add other services later (providers, worker pods, frontend static server), keep them in this namespace so `kubectl apply -f deploy/k8s` orchestrates the full stack.
