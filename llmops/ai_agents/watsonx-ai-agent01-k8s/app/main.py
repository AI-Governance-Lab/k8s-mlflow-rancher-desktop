from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
import os
import requests
from pydantic import BaseModel, Field
from typing import Optional
from fastapi import HTTPException

APP_NAME = "watsonx-ai-agent01"

API_URL = os.getenv("WATSONX_API_URL", "https://eu-de.ml.cloud.ibm.com").rstrip("/")
PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
LLM_MODEL_ID = os.getenv("WATSONX_LLM_MODEL_ID", "mistralai/mistral-large")
EMBED_MODEL_ID = os.getenv("WATSONX_EMBEDDING_MODEL_ID", "ibm/slate-125m-english-rtrvr")
IBM_API_KEY = os.getenv("IBMCLOUD_API_KEY", "")
VERIFY_TLS = os.getenv("WATSONX_VERIFY_TLS", "true").lower() != "false"
WATSONX_USE_CHAT = os.getenv("WATSONX_USE_CHAT", "false").lower() == "true"   # use chat endpoint instead of generation
WATSONX_USE_SDK = os.getenv("WATSONX_USE_SDK", "false").lower() == "true"     # opt-in to SDK

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
WX_API_VERSION = os.getenv("WATSONX_API_VERSION", "2023-05-29")
WATSONX_GENERATE_URL = f"{API_URL}/ml/v1/text/generation?version={WX_API_VERSION}"
WATSONX_CHAT_URL = f"{API_URL}/ml/v1/text/chat?version={WX_API_VERSION}"
WATSONX_EMBED_URL = f"{API_URL}/ml/v1/text/embeddings?version={WX_API_VERSION}"

# Optional MLflow flags (not used here, just placeholders)
MLFLOW_AUTO_LOG = os.getenv("MLFLOW_AUTO_LOG", "false").lower() == "true"
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "ai-agent01")

# Try to load SDK; fall back to HTTP if unavailable
SDK_AVAILABLE = False
try:
    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import Model
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    SDK_AVAILABLE = True
except Exception:
    SDK_AVAILABLE = False

app = FastAPI(
    title=APP_NAME,
    version="1.0.0",
    description="FastAPI agent with watsonx.ai. Use /docs to test.",
)

class GenRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 128
    temperature: float = 0.7
    top_p: Optional[float] = None
    top_k: Optional[int] = Field(default=None, ge=1, example=1, description="If set, must be >= 1")
    # Default 1.0 so /docs shows 1 and requests are valid by default
    repetition_penalty: Optional[float] = Field(default=1.0, ge=1.0, example=1.0, description="If set, must be >= 1.0")
    stop_sequences: Optional[list[str]] = None
    model_id: Optional[str] = Field(default=None, example=None)

def _get_iam_token() -> str:
    if not IBM_API_KEY:
        raise HTTPException(status_code=500, detail="IBMCLOUD_API_KEY is not set")
    try:
        resp = requests.post(
            IAM_TOKEN_URL,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": IBM_API_KEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
            verify=VERIFY_TLS,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IAM token error: {e}")

def _sanitize_model_id(model_id: Optional[str], default_id: str) -> str:
    mid = (model_id or "").strip()
    if mid == "" or mid.lower() in {"string", "default", "model"}:
        return default_id
    return mid

def _build_params(req: GenRequest) -> dict:
    params = {
        "max_new_tokens": req.max_new_tokens,
        "temperature": req.temperature,
    }
    if req.top_p is not None:
        params["top_p"] = req.top_p
    # Only include top_k if provided and >= 1
    if req.top_k is not None and req.top_k >= 1:
        params["top_k"] = req.top_k
    if req.repetition_penalty is not None:
        params["repetition_penalty"] = req.repetition_penalty
    if req.stop_sequences:
        params["stop_sequences"] = req.stop_sequences
    # Optional decoding hint
    params["decoding_method"] = "sample" if (req.temperature or 0) > 0 else "greedy"
    return params

def _generate_via_http(req: GenRequest) -> str:
    token = _get_iam_token()
    endpoint = WATSONX_CHAT_URL if WATSONX_USE_CHAT else WATSONX_GENERATE_URL
    model_id = _sanitize_model_id(req.model_id, LLM_MODEL_ID)
    params = _build_params(req)

    if WATSONX_USE_CHAT:
        payload = {
            "model_id": model_id,
            "project_id": PROJECT_ID,
            "parameters": params,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": req.prompt}]}
            ],
        }
    else:
        payload = {
            "model_id": model_id,
            "project_id": PROJECT_ID,
            "input": req.prompt,
            "parameters": params,
        }

    try:
        r = requests.post(
            endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
            verify=VERIFY_TLS,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            if "results" in data and data["results"]:
                return data["results"][0].get("generated_text") or data["results"][0].get("text", "")
            if "output" in data:
                out = data["output"]
                if isinstance(out, dict) and "text" in out:
                    return out["text"]
        return str(data)
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", 502)
        try:
            detail = e.response.json()
        except Exception:
            detail = getattr(e.response, "text", str(e))
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"watsonx request error: {e}")

def _generate_via_sdk(req: GenRequest) -> str:
    if not SDK_AVAILABLE:
        raise HTTPException(status_code=500, detail="ibm-watsonx-ai SDK not available")
    creds = Credentials(url=API_URL, api_key=IBM_API_KEY)
    model = Model(
        model_id=req.model_id or LLM_MODEL_ID,
        credentials=creds,
        project_id=PROJECT_ID,
        params={
            GenParams.MAX_NEW_TOKENS: req.max_new_tokens,
            GenParams.TEMPERATURE: req.temperature,
            **({GenParams.TOP_P: req.top_p} if req.top_p is not None else {}),
            **({GenParams.TOP_K: req.top_k} if req.top_k is not None else {}),
            **({GenParams.REPETITION_PENALTY: req.repetition_penalty} if req.repetition_penalty is not None else {}),
            **({GenParams.STOP_SEQUENCES: req.stop_sequences} if req.stop_sequences else {}),
        },
    )
    return model.generate_text(prompt=req.prompt)

@app.get("/", include_in_schema=False)
async def redirect_to_docs():
    return RedirectResponse(url="/docs")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url=app.openapi_url, title="API Docs")

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(openapi_url=app.openapi_url, title="API Docs")

@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME}

@app.get("/example")
async def read_example():
    return {"message": "This is an example endpoint."}

@app.post("/v1/generate")
def generate(req: GenRequest):
    try:
        text = _generate_via_http(req) if not (WATSONX_USE_SDK and SDK_AVAILABLE) else _generate_via_sdk(req)
        effective_model = _sanitize_model_id(req.model_id, LLM_MODEL_ID)
        return {"text": text, "model_id": effective_model}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
