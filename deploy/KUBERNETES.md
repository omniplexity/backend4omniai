# OmniAI Kubernetes Deployment Guide

This guide covers deploying OmniAI to Kubernetes using Helm or Kustomize.

## Prerequisites

- Kubernetes cluster (1.25+)
- kubectl configured
- Helm 3.13+ (for Helm deployment)
- Ingress controller (nginx, traefik, etc.)
- cert-manager (for automatic TLS)

## Deployment Options

### Option 1: Helm Chart (Recommended)

#### 1. Add Dependencies

```bash
cd deploy/helm/omniai
helm dependency update
```

#### 2. Create Secrets

```bash
# Create namespace
kubectl create namespace omniai

# Create secret for sensitive values
kubectl create secret generic omniai-secrets \
  --namespace omniai \
  --from-literal=secret-key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))") \
  --from-literal=database-url="postgresql://omniai:YOUR_PASSWORD@postgres:5432/omniai" \
  --from-literal=redis-url="redis://redis:6379/0"
```

#### 3. Install with Custom Values

```bash
# Basic installation
helm install omniai . \
  --namespace omniai \
  --set backend.ingress.enabled=true \
  --set backend.ingress.hosts[0].host=omniai.yourdomain.com \
  --set backend.secrets.existingSecret=omniai-secrets

# Production installation with overrides
helm install omniai . \
  --namespace omniai \
  -f values.yaml \
  -f values-production.yaml
```

#### 4. Verify Installation

```bash
kubectl get pods -n omniai
kubectl get svc -n omniai
kubectl get ingress -n omniai
```

#### 5. Upgrade

```bash
helm upgrade omniai . \
  --namespace omniai \
  --set backend.image.tag=1.1.0
```

### Option 2: Kustomize

#### Development Environment

```bash
kubectl apply -k deploy/k8s/overlays/dev
```

#### Staging Environment

```bash
# Create secrets first
kubectl create namespace omniai-staging
kubectl create secret generic staging-omniai-secrets \
  --namespace omniai-staging \
  --from-literal=secret-key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))") \
  --from-literal=database-url="postgresql://..." \
  --from-literal=redis-url="redis://..."

# Apply
kubectl apply -k deploy/k8s/overlays/staging
```

#### Production Environment

```bash
# Create namespace and secrets
kubectl create namespace omniai-prod
kubectl create secret generic prod-omniai-secrets \
  --namespace omniai-prod \
  --from-literal=secret-key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

# Apply with caution!
kubectl apply -k deploy/k8s/overlays/prod
```

## Configuration

### Values File (Helm)

Create a `values-production.yaml`:

```yaml
backend:
  replicaCount: 3
  
  image:
    tag: "1.0.0"
  
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: "letsencrypt-prod"
      nginx.ingress.kubernetes.io/ssl-redirect: "true"
      nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    hosts:
      - host: omniai.yourdomain.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - hosts:
          - omniai.yourdomain.com
        secretName: omniai-tls
  
  resources:
    limits:
      cpu: 4000m
      memory: 8Gi
    requests:
      cpu: 1000m
      memory: 2Gi
  
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
  
  env:
    ENVIRONMENT: production
    DEBUG: "false"
    LOG_LEVEL: WARNING
    INVITE_REQUIRED: "true"
    BOOTSTRAP_ADMIN_ENABLED: "false"
    COOKIE_SECURE: "true"
    COOKIE_SAMESITE: lax

postgresql:
  auth:
    password: "CHANGE_ME_STRONG_PASSWORD"
  primary:
    persistence:
      size: 50Gi
    resources:
      limits:
        cpu: 4000m
        memory: 8Gi
      requests:
        cpu: 500m
        memory: 1Gi

redis:
  master:
    persistence:
      size: 16Gi
```

### Secrets Management

#### Option A: kubectl create secret (Simple)

```bash
kubectl create secret generic omniai-secrets \
  --namespace omniai \
  --from-literal=secret-key="..." \
  --from-literal=database-url="..." \
  --from-file=credentials.json
```

#### Option B: Sealed Secrets (Production)

```bash
# Install kubeseal
# Encrypt secret
kubeseal --controller-namespace=sealed-secrets \
  --controller-name=sealed-secrets \
  < secret.yaml > sealed-secret.yaml

# Apply sealed secret
kubectl apply -f sealed-secret.yaml
```

#### Option C: External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: omniai-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-backend
  target:
    name: omniai-secrets
    creationPolicy: Owner
  data:
    - secretKey: secret-key
      remoteRef:
        key: omniai/production
        property: secret-key
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n omniai
kubectl describe pod <pod-name> -n omniai
kubectl logs <pod-name> -n omniai --tail=100
```

### Database Connection Issues

```bash
# Check if PostgreSQL is ready
kubectl get pods -l app.kubernetes.io/name=postgresql -n omniai

# Port forward to test connection
kubectl port-forward svc/omniai-postgresql 5432:5432 -n omniai
psql -h localhost -U omniai -d omniai
```

### Ingress Issues

```bash
# Check ingress status
kubectl get ingress -n omniai
kubectl describe ingress omniai -n omniai

# Check cert-manager certificates
kubectl get certificates -n omniai
kubectl describe certificate omniai-tls -n omniai
```

## Maintenance

### Backup Database

```bash
# Create backup job
kubectl create job --from=cronjob/omniai-backup manual-backup-$(date +%s) -n omniai

# Or manual pg_dump
kubectl exec -it deployment/omniai-postgresql -- pg_dump -U omniai omniai > backup.sql
```

### Update Deployment

```bash
# Rolling update
kubectl set image deployment/omniai-backend backend=omniai/backend:1.1.0 -n omniai

# Watch rollout
kubectl rollout status deployment/omniai-backend -n omniai

# Rollback if needed
kubectl rollout undo deployment/omniai-backend -n omniai
```

### Scale Deployment

```bash
# Manual scaling
kubectl scale deployment omniai-backend --replicas=5 -n omniai

# With HPA
kubectl get hpa -n omniai
```

## Security Considerations

1. **Network Policies**: Restrict pod-to-pod communication
2. **Pod Security**: Use restricted Pod Security Standards
3. **RBAC**: Limit service account permissions
4. **Secrets**: Use external secret management
5. **Monitoring**: Enable audit logging

## Resources

- [Helm Documentation](https://helm.sh/docs/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [cert-manager Documentation](https://cert-manager.io/docs/)
