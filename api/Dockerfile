FROM python:3.12-slim-bookworm

# 워커가 docker compose / git 을 쓴다. API 컨테이너도 같은 이미지지만 Docker 소켓은 받지 않는다.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .
ENV PYTHONUNBUFFERED=1
