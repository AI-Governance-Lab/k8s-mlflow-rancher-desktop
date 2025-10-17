# 🧱 LocalStack S3 Setup on Kubernetes (Rancher Desktop)

## 📋 Requirements

- Kubernetes cluster (Rancher Desktop, K3s, RKE2 etc.)
- `kubectl` configured
- MLflow or FastAPI (optional)
- Docker Hub access (for pulling LocalStack image)

---

## 🚀 Install

```bash
kubectl apply -f localstack-deployment.yaml


This will:
- Deploy LocalStack with S3 service
- Expose it on http://localhost:31566
- Create bucket mlflow-artifacts
- Apply permissive CORS config for browser access

🧪 Validate
Check pod status
kubectl get pods -l app=localstack


List bucket contents
kubectl exec -it <localstack-pod> -- \
  aws --endpoint-url=http://localhost:4566 s3 ls s3://mlflow-artifacts --recursive


Test CORS config
kubectl exec -it <localstack-pod> -- \
  aws --endpoint-url=http://localhost:4566 s3api get-bucket-cors --bucket mlflow-artifacts



🔗 MLflow Integration
Set environment variables:
export MLFLOW_S3_ENDPOINT_URL=http://localhost:31566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test


Then log artifacts:
import mlflow
with mlflow.start_run():
    mlflow.log_artifact("metrics.json", artifact_path="metrics")

Ex:

import mlflow
mlflow.set_tracking_uri("http://localhost:5000")  # dacă rulezi MLflow UI local
mlflow.set_experiment("demo")

with mlflow.start_run():
    with open("metrics.json", "w") as f:
        f.write('{"accuracy": 0.92}')
    mlflow.log_artifact("metrics.json", artifact_path="metrics")



🧹 Uninstall
kubectl delete deployment localstack
kubectl delete service localstack
kubectl delete configmap localstack-cors
kubectl delete job localstack-init


Optional: remove PVCs or volumes if used.

🧩 Notes
- Bucket name: mlflow-artifacts
- Port exposed: 31566
- CORS: AllowedOrigins=["*"], AllowedMethods=["GET", "PUT", "POST", "DELETE"]
- Credentials: test:test (mocked for LocalStack)

🛠️ Troubleshooting
- If pod is stuck in ContainerCreating, use:
kubectl describe pod <localstack-pod>
- If image fails to pull, switch to:
image: localstack/localstack:3.0
- If CORS fails, ensure bucket exists and cors.json is mounted correctly.

---


