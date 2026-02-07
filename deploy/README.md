# OmniAI Deployment

This directory contains all deployment configurations for OmniAI, supporting multiple deployment methods from local development to production Kubernetes clusters.

## Quick Start

### Local Development (Docker Compose)

```bash
cd OmniAI-backend
docker compose up -d
```

### Production (Kubernetes + Helm)

```bash
cd deploy/helm/omniai
helm dependency update
helm install omniai . --namespace omniai --create-namespace
```

## Deployment Options

| Method | Best For | Complexity | Scaling |
|--------|----------|------------|---------|
| [Docker Compose](../OmniAI-backend/docker-compose.yml) | Local dev, single server | Low | Manual |
| [Docker + Nginx](nginx/) | Small production | Low-Medium | Manual |
| [Docker + Caddy](caddy/) | Small-Medium production | Low | Manual |
| [Docker + Traefik](traefik/) | Medium production | Medium | Manual |
| [Helm + K8s](helm/omniai/) | Large production | Medium-High | Auto |
| [Kustomize](k8s/) | GitOps, multi-env | Medium | Auto |

## Directory Structure

```
deploy/
├── README.md                    # This file
├── .env.development            # Development environment template
├── .env.staging                # Staging environment template
├── .env.production             # Production environment template
├── KUBERNETES.md               # Kubernetes deployment guide
│
├── helm/omniai/                # Helm Chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── hpa.yaml
│       ├── configmap.yaml
│       ├── secret.yaml
│       ├── pvc.yaml
│       └── serviceaccount.yaml
│
├── k8s/                        # Kustomize templates
│   ├── base/                   # Base resources
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── pvc.yaml
│   │   └── serviceaccount.yaml
│   └── overlays/
│       ├── dev/                # Development overlay
│       ├── staging/            # Staging overlay
│       └── prod/               # Production overlay
│
├── nginx/                      # Nginx reverse proxy
│   ├── nginx.conf
│   └── docker-compose.nginx.yml
│
├── caddy/                      # Caddy reverse proxy
│   ├── Caddyfile
│   └── docker-compose.caddy.yml
│
└── traefik/                    # Traefik reverse proxy
    ├── traefik.yml
    ├── docker-compose.traefik.yml
    └── dynamic/
        └── middlewares.yml
```

## Environment Configuration

Choose the appropriate environment file for your deployment:

| Environment | File | Purpose |
|-------------|------|---------|
| Development | `.env.development` | Local development with SQLite |
| Staging | `.env.staging` | Pre-production testing with PostgreSQL |
| Production | `.env.production` | Production with full security |

## CI/CD Pipelines

GitHub Actions workflows are configured in `.github/workflows/`:

- **backend-ci.yml** - Lint, type check, test, build backend
- **frontend-ci.yml** - Type check, build, E2E tests, deploy to GitHub Pages
- **integration.yml** - Docker Compose stack tests, API contract tests
- **release.yml** - Multi-arch Docker builds, Helm chart packaging, releases

## Security Checklist

Before deploying to production:

- [ ] Change all default passwords
- [ ] Generate strong SECRET_KEY (64+ chars)
- [ ] Configure CORS_ORIGINS to your domain only
- [ ] Enable COOKIE_SECURE and use HTTPS
- [ ] Disable BOOTSTRAP_ADMIN_ENABLED after setup
- [ ] Enable INVITE_REQUIRED for user registration
- [ ] Set up proper TLS certificates
- [ ] Configure rate limiting
- [ ] Set up monitoring and alerting
- [ ] Enable database backups
- [ ] Review security headers

## Scaling Guide

### Vertical Scaling (Docker Compose)

Edit `resources` in docker-compose.yml:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
```

### Horizontal Scaling (Kubernetes)

Enable HPA in Helm values:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

## Monitoring

### Health Endpoints

- `GET /health` - Liveness probe
- `GET /readyz` - Readiness probe
- `GET /api/diag/lite` - Lightweight health check
- `GET /api/diag` - Full diagnostics (admin only)

### Prometheus Metrics

When using Traefik, metrics are exposed at `:8082/metrics`.

## Troubleshooting

### Common Issues

1. **Database connection fails**
   - Check DATABASE_URL format
   - Verify PostgreSQL is running
   - Check credentials

2. **CORS errors**
   - Verify CORS_ORIGINS includes your frontend domain
   - Check protocol (http vs https)

3. **Cookie not set**
   - Ensure COOKIE_SECURE matches your protocol
   - Check COOKIE_SAMESITE for cross-site requests

4. **Provider health check fails**
   - Verify LM Studio/Ollama is running
   - Check PROVIDERS_ENABLED list
   - Review provider base URLs

See [KUBERNETES.md](KUBERNETES.md) for Kubernetes-specific troubleshooting.

## Contributing

When adding new deployment methods:

1. Create a new subdirectory with clear naming
2. Include docker-compose.yml or equivalent
3. Add configuration examples
4. Update this README with the new option
5. Test locally before committing

## Resources

- [OmniAI Main README](../README.md)
- [Deployment Guide](../DEPLOY.md)
- [Kubernetes Guide](KUBERNETES.md)
