# 🧱 LocalStack S3 Setup on Kubernetes (Rancher Desktop)

## 📋 Requirements
- Kubernetes cluster (Rancher Desktop, K3s, RKE2, etc.)
- kubectl configured
- Docker Hub access (for pulling LocalStack image)
- Optional: MLflow or FastAPI app

---

## 🚀 Install
```bash
kubectl apply -f localstack-deployment.yaml
kubectl wait --for=condition=ready pod -l app=localstack --timeout=60s
kubectl apply -f localstack-init-job.yaml
```

This will:
- Deploy LocalStack with S3 service
- Expose it on http://localhost:31566 (NodePort)
- Create bucket mlflow-artifacts
- Apply permissive CORS for browser access

---

## 🧪 Validate

Check pod and service
```bash
kubectl get pods -l app=localstack
kubectl get svc localstack
```

List bucket contents (from your machine)
```bash
aws --endpoint-url=http://localhost:31566 s3 ls s3://mlflow-artifacts --recursive
```

Test CORS config (inside the pod, using the internal 4566 port)
```bash
POD=$(kubectl get pods -l app=localstack -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it "$POD" -- \
  aws --endpoint-url=http://localhost:4566 s3api get-bucket-cors --bucket mlflow-artifacts
```

---

## 🔗 MLflow Integration

Local MLflow (running on your machine)
```bash
export MLFLOW_S3_ENDPOINT_URL=http://localhost:31566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export AWS_S3_FORCE_PATH_STYLE=true
```

Python example
```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("demo")

with mlflow.start_run():
    with open("metrics.json", "w") as f:
        f.write('{"accuracy": 0.92}')
    mlflow.log_artifact("metrics.json", artifact_path="metrics")
```

In-cluster MLflow (use the ClusterIP/port inside the cluster)
```bash
# Example env injection on an existing Deployment named "mlflow" (namespace mlflow)
kubectl -n mlflow set env deploy/mlflow \
  MLFLOW_S3_ENDPOINT_URL=http://localstack.localstack.svc.cluster.local:4566 \
  AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  AWS_DEFAULT_REGION=us-east-1 AWS_S3_FORCE_PATH_STYLE=true
kubectl -n mlflow rollout restart deploy/mlflow
```

---

## ✅ Sample checks

List artifacts (from your machine)
```bash
aws --endpoint-url=http://localhost:31566 s3 ls s3://mlflow-artifacts --recursive
```

List buckets (from your machine)
```bash
aws --endpoint-url=http://localhost:31566 s3api list-buckets
```

Example output
```json
{
  "Buckets": [
    {
      "Name": "mlflow-artifacts",
      "CreationDate": "2025-10-17T13:54:37+00:00"
    }
  ],
  "Owner": {
    "DisplayName": "webfile",
    "ID": "75aa57f09aa0c8caeab4f8c24e99d10f8e7faeebf76c078efc7c6caea54ba06a"
  },
  "Prefix": null
}
```

End-to-end validation (Python)
```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("demo")

with mlflow.start_run():
    with open("metrics.json", "w") as f:
        f.write('{"accuracy": 0.92}')
    mlflow.log_artifact("metrics.json", artifact_path="metrics")
```

---

## 🧹 Uninstall
```bash
kubectl delete job localstack-init
kubectl delete configmap localstack-cors
kubectl delete service localstack
kubectl delete deployment localstack
```

Optional: remove PVCs/volumes if you created any.

---

## 🛠️ Troubleshooting
- Pod stuck in ContainerCreating:
  ```bash
  kubectl describe pod -l app=localstack
  ```
- Image pull issues: ensure image tag exists (e.g., localstack/localstack:3.0).
- CORS errors:
  - Verify bucket exists: mlflow-artifacts
  - Confirm cors.json is mounted and the init job completed
- If NodePort 31566 is occupied, change the Service NodePort or use port-forward:
  ```bash
  kubectl port-forward svc/localstack 31566:4566
  ```