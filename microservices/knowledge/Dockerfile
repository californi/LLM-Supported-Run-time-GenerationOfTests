FROM python:3.9-slim

WORKDIR /app

# Instalar dependências
RUN pip install fastapi uvicorn redis requests

# Copiar código
COPY app.py .

# Criar diretório de logs
RUN mkdir -p /app/logs/knowledge

# Expor porta
EXPOSE 8000

# Comando de inicialização
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
