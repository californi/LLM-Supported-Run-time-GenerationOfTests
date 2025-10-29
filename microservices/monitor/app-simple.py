#!/usr/bin/env python3
"""
Monitor Simples - Versão v17.5.0
Coleta métricas básicas do cluster Kubernetes
"""

import subprocess
import json
import time
import logging
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
import requests

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Monitor Simples", version="v17.8.1")

def get_cluster_resources() -> Dict[str, float]:
    """Coleta recursos REAIS do cluster - SEM FALLBACKS"""
    try:
        # Obter recursos do cluster via kubectl top nodes
        result = subprocess.run(
            ["kubectl", "top", "nodes", "--no-headers"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            raise Exception(f"kubectl top nodes falhou: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        total_cpu_millicores = 0
        total_memory_bytes = 0
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:  # NODE_NAME CPU CPU% MEMORY MEMORY%
                try:
                    cpu_val = int(parts[1].replace('m', ''))
                    memory_val = int(parts[3].replace('Mi', ''))
                    total_cpu_millicores += cpu_val
                    total_memory_bytes += memory_val * 1024 * 1024
                except ValueError as e:
                    logger.error(f"Erro ao processar linha: {line}, erro: {e}")
                    continue
        
        # Obter capacidade REAL do cluster
        capacity_result = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.capacity.cpu},{.items[0].status.capacity.memory}"],
            capture_output=True, text=True, timeout=30
        )
        
        if capacity_result.returncode != 0:
            raise Exception(f"Não foi possível obter capacidade real do cluster: {capacity_result.stderr}")
        
        capacity_parts = capacity_result.stdout.strip().replace('"', '').split(',')
        total_cpu_cores = int(capacity_parts[0])
        total_memory_bytes_capacity = int(capacity_parts[1].replace('Ki', '')) * 1024  # Converter Ki para bytes
        
        cpu_usage_percent = (total_cpu_millicores / (total_cpu_cores * 1000)) * 100
        memory_usage_percent = (total_memory_bytes / total_memory_bytes_capacity) * 100
        
        return {
            "cluster_cpu_usage_percent": round(cpu_usage_percent, 2),
            "cluster_memory_usage_percent": round(memory_usage_percent, 2),
            "allocated_cpus": total_cpu_cores,
            "allocated_memory": total_memory_bytes_capacity // (1024**3)  # Converter para GB
        }
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao obter recursos do cluster: {e}")
        raise Exception(f"Não foi possível coletar recursos reais do cluster: {e}")

def get_kube_znn_metrics() -> Dict[str, Any]:
    """Coleta métricas REAIS do kube-znn-nginx - SEM FALLBACKS"""
    try:
        # Obter métricas de CPU/Memory dos pods REAIS
        result = subprocess.run(
            ["kubectl", "top", "pods", "-l", "app=kube-znn-nginx", "--no-headers"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            raise Exception(f"kubectl top pods falhou: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        total_cpu_millicores = 0
        total_memory_mb = 0
        target_system_pods = len(lines)
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    total_cpu_millicores += int(parts[1].replace('m', ''))
                    total_memory_mb += int(parts[2].replace('Mi', ''))
                except ValueError:
                    continue
        
        # Obter limites dos pods para calcular percentuais REAIS
        limits_result = subprocess.run(
            ["kubectl", "get", "pods", "-l", "app=kube-znn-nginx", "-o", "jsonpath={range .items[*]}{.spec.containers[0].resources.limits.cpu},{.spec.containers[0].resources.limits.memory}{'\\n'}{end}"],
            capture_output=True, text=True, timeout=30
        )
        
        if limits_result.returncode != 0 or not limits_result.stdout.strip():
            raise Exception("Não foi possível obter limites dos pods ZNN")
        
        total_cpu_limit_millicores = 0
        total_memory_limit_mb = 0
        
        limit_lines = limits_result.stdout.strip().split('\n')
        for limit_line in limit_lines:
            if limit_line.strip():
                parts = limit_line.split(',')
                if len(parts) >= 2:
                    # CPU limit
                    cpu_limit = parts[0]
                    if cpu_limit.endswith('m'):
                        total_cpu_limit_millicores += int(cpu_limit[:-1])
                    elif cpu_limit.endswith('n'):
                        total_cpu_limit_millicores += int(cpu_limit[:-1]) // 1000000
                    else:
                        total_cpu_limit_millicores += int(cpu_limit) * 1000
                    
                    # Memory limit
                    memory_limit = parts[1]
                    if memory_limit.endswith('Mi'):
                        total_memory_limit_mb += int(memory_limit[:-2])
                    elif memory_limit.endswith('Gi'):
                        total_memory_limit_mb += int(memory_limit[:-2]) * 1024
                    elif memory_limit.endswith('Ki'):
                        total_memory_limit_mb += int(memory_limit[:-2]) // 1024
        
        if total_cpu_limit_millicores == 0 or total_memory_limit_mb == 0:
            raise Exception("Não foi possível obter limites válidos dos pods ZNN")
        
        kube_znn_cpu_usage_percent = (total_cpu_millicores / total_cpu_limit_millicores) * 100
        kube_znn_memory_usage_percent = (total_memory_mb / total_memory_limit_mb) * 100
        
        # Testar resposta REAL do kube-znn-nginx
        start_time = time.time()
        response = requests.get("http://kube-znn-nginx:80", timeout=30)
        response_time_ms = (time.time() - start_time) * 1000
        
        return {
            "kube_znn_cpu_usage_percent": round(kube_znn_cpu_usage_percent, 2),
            "kube_znn_memory_usage_percent": round(kube_znn_memory_usage_percent, 2),
            "kube_znn_response_time_ms": round(response_time_ms, 2),
            "target_system_pods": target_system_pods,
            "kube_znn_processing_percent": round(min(kube_znn_memory_usage_percent, 100), 2)
        }
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao obter métricas do kube-znn: {e}")
        raise Exception(f"Não foi possível coletar métricas reais do kube-znn: {e}")

def get_load_generator_status() -> Dict[str, Any]:
    """Obtém status REAL do load generator - SEM FALLBACKS"""
    try:
        response = requests.get("http://load-generator:8000/status", timeout=30)
        if response.status_code != 200:
            raise Exception(f"Load generator retornou status {response.status_code}")
        
        data = response.json()
        
        # Verificar se os dados são válidos
        if "current_users" not in data or "request_rate" not in data or "load_pattern" not in data:
            raise Exception("Load generator não retornou dados completos")
        
        return {
            "concurrent_users": data["current_users"],
            "request_rate": data["request_rate"],
            "load_pattern": data["load_pattern"]
        }
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao obter status do load generator: {e}")
        raise Exception(f"Não foi possível obter status real do load generator: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint - apenas timestamp real"""
    return {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

@app.get("/monitor/metrics")
async def get_metrics():
    """Endpoint principal para coleta de métricas - APENAS DADOS REAIS"""
    try:
        # Coletar métricas REAIS
        cluster_metrics = get_cluster_resources()
        kube_znn_metrics = get_kube_znn_metrics()
        load_status = get_load_generator_status()
        
        # Calcular métricas derivadas REAIS
        throughput = load_status["concurrent_users"] * load_status["request_rate"]
        
        # Montar resposta APENAS com dados REAIS
        metrics = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "service": "monitor",
            "version": "v17.8.1",
            
            # Métricas REAIS do cluster
            **cluster_metrics,
            
            # Métricas REAIS do kube-znn
            **kube_znn_metrics,
            
            # Métricas REAIS de carga
            **load_status,
            "throughput": throughput,
            
            # Identificadores únicos REAIS
            "run_id": f"run_{int(time.time())}",
            "unique_loop_id": f"loop_{int(time.time())}"
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Erro ao coletar métricas: {e}")
        raise HTTPException(status_code=500, detail=f"Não foi possível coletar métricas reais: {e}")

@app.get("/")
async def root():
    """Endpoint raiz - apenas versão real"""
    return {
        "service": "Monitor Simples",
        "version": "v17.8.1"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
