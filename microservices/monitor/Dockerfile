FROM python:3.9-slim

WORKDIR /app

# Install system dependencies including curl, apache2-utils and kubectl
RUN apt-get update && apt-get install -y \
    curl \
    apache2-utils \
    ca-certificates \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app-simple.py app.py

# Criar diretório de logs
RUN mkdir -p /app/logs/monitor

# Expor porta
EXPOSE 8000

# Comando de inicialização
CMD ["python", "app.py"]