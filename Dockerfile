# Gold AI Trading Bot — container image
# Build:  docker build -t goldbot .
# Jalan paling enak lewat docker-compose (lihat docker-compose.yml).
FROM python:3.12-slim

# Tooling minimal untuk build wheel pandas/numpy + healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer dependency dulu (cache build lebih cepat saat kode berubah)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Kode bot
COPY . .

# State persisten (lessons, evaluations, paper_state) ditulis ke sini -> volume
VOLUME ["/app/bot_memory"]

# Buffering off biar log langsung kebaca di `docker logs`
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
