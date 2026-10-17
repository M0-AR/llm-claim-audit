FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the o200k_base vocabulary into the image so the snapshot pipeline
# (network_mode: "none") can run E4 offline. The assert pins the artifact.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN mkdir -p /opt/tiktoken-cache && \
    python -c "import tiktoken; enc = tiktoken.get_encoding('o200k_base'); assert enc.n_vocab == 200019, enc.n_vocab"

COPY . .

CMD ["python", "scripts/run_all.py", "--mode", "snapshot"]
