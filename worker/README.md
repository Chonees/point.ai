# Point.ai GPU Worker

FastAPI inference worker that serves the `/infer/structure` contract.

## Backends

| `POINTAI_MODEL_BACKEND` | Requires | Status |
|---|---|---|
| `heuristic` (default) | OpenCV only | Ready |
| `cubicasa5k` | PyTorch + CubiCasa5k weights | Stub — implement `_load_cubicasa5k()` |
| `floortrans` | PyTorch + FloorTransNet weights | Stub — implement `_load_floortrans()` |

## Run locally (heuristic)

```bash
cd worker/
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8100
```

## Run with Docker

```bash
docker build -t pointai-worker .
docker run -p 8100:8100 \
  -e POINTAI_MODEL_BACKEND=heuristic \
  pointai-worker
```

## Connect to main backend

Set in `.env`:
```
POINTAI_INFERENCE_BACKEND=remote
POINTAI_WORKER_URL=http://localhost:8100
```

## Integrating a real GPU model

1. Add model package (e.g. `cubicasa5k/`) to this directory
2. Implement `_load_cubicasa5k(weights_path)` in `server.py`
3. Set `POINTAI_MODEL_WEIGHTS=/path/to/weights.pth`
4. Implement `_model_infer(model, image)` — convert segmentation masks to walls/openings contract
5. Set `POINTAI_MODEL_BACKEND=cubicasa5k`
