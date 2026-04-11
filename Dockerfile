FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY scripts/download_weights.py ./scripts/download_weights.py

ENV POINTAI_MITUNET_WEIGHTS=/app/weights/mitunet_finetune.pth
ENV POINTAI_CUBICASA_ROOT=/app/cubicasa
ENV POINTAI_INFERENCE_BACKEND=ensemble_local
ENV PORT=8000

EXPOSE ${PORT}
CMD python scripts/download_weights.py && uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}
