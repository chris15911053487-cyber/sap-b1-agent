FROM python:3.11-slim-bookworm

LABEL maintainer="SAP B1 Consultant"
LABEL description="SAP Business One AI Database Agent"

# 安装 FreeTDS（pymssql 依赖，纯 TDS 协议，不经过 ODBC/OpenSSL）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates \
    freetds-dev freetds-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

RUN mkdir -p /app/config /app/logs /app/data

RUN useradd --create-home --shell /bin/bash agent && chown -R agent:agent /app
USER agent

ENTRYPOINT ["python", "main.py"]
