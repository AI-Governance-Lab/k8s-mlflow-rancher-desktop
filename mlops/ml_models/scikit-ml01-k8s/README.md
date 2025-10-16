# scikit-ml01-k8s (FastAPI + MLflow)

Basic FastAPI model service (Iris) integrated with MLflow. Deployable via Helm.

## Prerequisites
- kubectl and Helm configured
- MLflow reachable from the cluster

## 1) Prepare runtime env
Create a local .env in this folder:
```env
# See .env.example for a template
```

## 2) Create namespace and Secret from .env (generate YAML, then apply)
```bash
# From this directory
kubectl create namespace mlops

# Generate a Secret manifest from ./.env (stored locally)
mkdir -p k8s
kubectl -n mlops create secret generic mlops-env \
  --from-env-file=.env \
  --dry-run=client -o yaml > k8s/mlops-env-secret.yaml

# Apply the Secret manifest
kubectl -n mlops apply -f k8s/mlops-env-secret.yaml
```

## 3) Deploy with Helm (image: crevesky/scikit-ml01-k8s:latest)
```bash
helm upgrade --install mlops ./helm/mlops -n mlops
```

## 4) Verify and test
```bash
kubectl get pods -n mlops
kubectl get svc -n mlops mlops

# If Service is ClusterIP, port-forward:
kubectl -n mlops port-forward svc/mlops 8000:8000

curl http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/predict -H "Content-Type: application/json" \
  -d '{"instances":[[5.1,3.5,1.4,0.2],[6.2,3.4,5.4,2.3]]}'
```

## 5) Update Secret and reload pods (when .env changes)

Option A) Update Secret in-place (no local YAML file)
```bash
kubectl -n mlops create secret generic mlops-env \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pods so new env vars are loaded
kubectl -n mlops rollout restart deployment/mlops
kubectl -n mlops rollout status deployment/mlops
```

Option B) Re-generate Secret YAML then apply
```bash
kubectl -n mlops create secret generic mlops-env \
  --from-env-file=.env \
  --dry-run=client -o yaml > k8s/mlops-env-secret.yaml
kubectl -n mlops apply -f k8s/mlops-env-secret.yaml

kubectl -n mlops rollout restart deployment/mlops
kubectl -n mlops rollout status deployment/mlops
```

Alternative: trigger a redeploy via Helm (if you prefer using Helm)
```bash
helm upgrade --install mlops ./helm/mlops -n mlops --reuse-values
kubectl -n mlops rollout status deployment/mlops
```

Verify the pod sees updated env vars
```bash
POD=$(kubectl get pods -n mlops -l app.kubernetes.io/name=mlops -o jsonpath="{.items[0].metadata.name}")
kubectl -n mlops exec "$POD" -- sh -lc 'env | egrep "MLFLOW_(TRACKING_URI|EXPERIMENT_NAME)"'
```

Note: Updating a Secret does not automatically restart pods. You must restart the Deployment to pick up the new values.

## 6) Uninstall
```bash
helm uninstall mlops -n mlops
kubectl delete namespace mlops
```

Notes:
- The chart expects a Secret named mlops-env (created above).
- Ensure MLflow is reachable from the cluster.