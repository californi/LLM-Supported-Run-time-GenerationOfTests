FROM python:3.9-slim

WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app.py .

# Criar diretório de logs
RUN mkdir -p /app/logs/llm-service

# Expor porta
EXPOSE 8000

# Variável de ambiente para o token Hugging Face
ENV HF_API_TOKEN=YOUR_HF_TOKEN_HERE

# Comando de inicialização
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
