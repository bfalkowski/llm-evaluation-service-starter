# Kubernetes Deployment Notes

These manifests are a small deployment starting point for local Kubernetes and managed
cluster experiments. They are intentionally plain YAML so the runtime shape is easy to
inspect before introducing Helm, Kustomize, or a separate deployment repository.

## Prerequisites

Use one local Kubernetes option:

- Docker Desktop Kubernetes
- kind
- minikube
- Colima with Kubernetes enabled

Confirm that `kubectl` can reach the cluster:

```bash
kubectl cluster-info
```

## Image Strategy

By default, `deployment.yaml` uses the image published by CI:

```text
ghcr.io/bfalkowski/llm-evaluation-service-starter:latest
```

That is the simplest path for a local cluster that can pull from GHCR.

For local image testing without pushing to a registry, build a local tag and point the
Deployment at it:

```bash
docker build -t ghcr.io/bfalkowski/llm-evaluation-service-starter:local .
```

For kind:

```bash
kind load docker-image ghcr.io/bfalkowski/llm-evaluation-service-starter:local
```

For minikube, build inside the minikube Docker environment instead:

```bash
eval "$(minikube docker-env)"
docker build -t ghcr.io/bfalkowski/llm-evaluation-service-starter:local .
```

After applying the manifests, switch the running Deployment to the local tag:

```bash
kubectl -n llm-evaluation set image \
  deployment/llm-evaluation-service \
  service=ghcr.io/bfalkowski/llm-evaluation-service-starter:local
```

## Configure Secrets

Copy the example secret and edit it before applying:

```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.local.yaml
```

`secret.local.yaml` is ignored by git. Do not commit real credentials.

For managed Kubernetes, replace the demo Postgres URL with a managed Postgres
connection string supplied by your platform's secret manager or deployment workflow.

## Apply Manifests

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secret.local.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/postgres.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

Check rollout status:

```bash
kubectl -n llm-evaluation rollout status deployment/llm-evaluation-service
kubectl -n llm-evaluation get pods
```

## Test The Service

Forward the service to your machine:

```bash
kubectl -n llm-evaluation port-forward service/llm-evaluation-service 8000:80
```

In another terminal:

```bash
curl -s http://localhost:8000/health/ready
```

Expected response:

```json
{"status":"ready"}
```

## Cleanup

Remove the demo namespace and all resources inside it:

```bash
kubectl delete namespace llm-evaluation
```

Remove the local secret file if it is no longer needed:

```bash
rm deploy/k8s/secret.local.yaml
```

## Production Notes

For a managed cluster, keep the same broad shape but replace the demo pieces:

- Use managed Postgres instead of the demo Postgres Deployment.
- Inject secrets from the platform or deployment pipeline.
- Pin image tags to immutable release tags or commit SHAs instead of `latest`.
- Add ingress, TLS, service accounts, network policies, and telemetry collector config.
- Move environment-specific values to the deployment/config repository when that repo exists.
