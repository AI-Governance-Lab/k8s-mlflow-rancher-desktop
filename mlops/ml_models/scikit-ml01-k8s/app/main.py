import os
import time
from typing import List, Dict, Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
import mlflow
import mlflow.sklearn

APP_NAME = "mlops-fastapi"
MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "mlops-basic")
TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")

app = FastAPI(title=APP_NAME)

class PredictRequest(BaseModel):
    instances: List[List[float]]

class PredictResponse(BaseModel):
    predictions: List[int]

_model = None

def _train_and_log() -> LogisticRegression:
    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = LogisticRegression(max_iter=500)
    start = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - start

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    try:
        if TRACKING_URI:
            mlflow.set_tracking_uri(TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
        with mlflow.start_run(run_name=f"{APP_NAME}-startup"):
            mlflow.log_param("model_type", "LogisticRegression")
            mlflow.log_param("dataset", "iris")
            mlflow.log_metric("accuracy", float(acc))
            mlflow.log_metric("train_time_sec", float(train_time))
            mlflow.sklearn.log_model(model, artifact_path="model")
    except Exception as e:
        # Keep serving even if MLflow is not reachable
        print(f"[WARN] MLflow logging skipped: {e}")

    return model

@app.on_event("startup")
def on_startup():
    global _model
    _model = _train_and_log()
    print("[INFO] Model trained and ready.")

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "app": APP_NAME}

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not ready")
    X = np.array(req.instances, dtype=float)
    if X.ndim != 2 or X.shape[1] != 4:
        raise HTTPException(status_code=400, detail="Expecting N x 4 feature matrix for Iris")
    preds = _model.predict(X)
    return PredictResponse(predictions=[int(p) for p in preds])

@app.get("/metrics")
def metrics() -> Dict[str, Any]:
    return {"experiment": MLFLOW_EXPERIMENT_NAME, "mlflow_uri": TRACKING_URI or ""}