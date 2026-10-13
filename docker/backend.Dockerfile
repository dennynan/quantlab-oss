FROM python:3.12-slim

# 编译 pyqlib / lightgbm / scipy 需要的工具链
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ cmake git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app

ENV PORT=5001 PYTHONUNBUFFERED=1
EXPOSE 5001

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
