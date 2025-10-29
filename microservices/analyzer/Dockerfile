FROM python:3.9-slim

# Instalar kubectl e apache2-utils
RUN apt-get update && apt-get install -y \
    curl \
    apache2-utils \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install fastapi uvicorn redis requests psutil

COPY . .

# Criar diretório de logs
RUN mkdir -p /app/logs/analyzer

EXPOSE 8000

CMD ["python", "app.py"]
