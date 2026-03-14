FROM python:3.11-slim

# System dependencies for OpenCV and PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV POINTAI_WORKER_MODEL_NAME=floorplan-seg-worker
ENV POINTAI_WORKER_MODEL_VERSION=1.0.0
ENV POINTAI_WORKER_READY=true
# Set to path of .pth weights file when using a real model:
# ENV POINTAI_MODEL_WEIGHTS=/app/weights/model.pth
# Set to "cubicasa5k" or "floortrans" to use ML backend:
ENV POINTAI_MODEL_BACKEND=heuristic

EXPOSE 8100
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
