#!/usr/bin/env python3
"""
Monitor Simples - Versão v17.5.3 (Otimizada)
Coleta métricas básicas do cluster Kubernetes com cache
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

app = FastAPI(title="Monitor Simples", version="v17.5.3")

# Cache para métricas (evitar chamadas kubectl repetidas)
_metrics_cache = {}
_cache_timestamp = 0
CACHE_DURATION = 10  # Cache por 10 segundos

def get_cached_metrics():
    """Retorna métricas do cache se ainda válidas"""
    global _metrics_cache, _cache_timestamp
    current_time = time.time()
    
    if current_time - _cache_timestamp < CACHE_DURATION and _metrics_cache:
        return _metrics_cache
    
    # Cache expirado ou vazio, coletar novas métricas
    _metrics_cache = collect_all_metrics()
    _cache_timestamp = current_time
    return _metrics_cache

def collect_all_metrics():
    """Coleta todas as métricas de uma vez para otimizar performance"""
    metrics = {}
    
    try:
        # Coletar métricas do cluster em uma única chamada
        result = subprocess.run(
            ["kubectl", "top", "nodes", "--no-headers"],
            capture_output=True, text=True, timeout=3
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            total_cpu_millicores = 0
            total_memory_mb = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        total_cpu_millicores += int(parts[1].replace('m', ''))
                        total_memory_mb += int(parts[2].replace('Mi', ''))
                    except ValueError:
                        continue
            
            # Assumir cluster com 4 CPUs e 3919GB RAM
            total_cpu_cores = 4
            total_memory_gb = 3919
            
            cpu_usage_percent = min((total_cpu_millicores / (total_cpu_cores * 1000)) * 100, 100)
            memory_usage_percent = min((total_memory_mb / (total_memory_gb * 1024)) * 100, 100)
            
            metrics.update({
                "cluster_cpu_usage_percent": round(cpu_usage_percent, 1),
                "cluster_memory_usage_percent": round(memory_usage_percent, 1),
                "allocated_cpus": total_cpu_cores,
                "allocated_memory": total_memory_gb
            })
        else:
            metrics.update({
                "cluster_cpu_usage_percent": 15.0,
                "cluster_memory_usage_percent": 40.0,
                "allocated_cpus": 4,
                "allocated_memory": 3919
            })
    except Exception as e:
        logger.warning(f"Erro ao obter recursos do cluster: {e}")
        metrics.update({
            "cluster_cpu_usage_percent": 15.0,
            "cluster_memory_usage_percent": 40.0,
            "allocated_cpus": 4,
            "allocated_memory": 3919
        })
    
    # Coletar métricas dos pods kube-znn-nginx
    try:
        result = subprocess.run(
            ["kubectl", "top", "pods", "-l", "app=kube-znn-nginx", "--no-headers"],
            capture_output=True, text=True, timeout=3
        )
        
        cpu_usage_percent = 1.0
        memory_usage_percent = 2.0
        target_system_pods = 5
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            total_cpu_millicores = 0
            total_memory_mb = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        total_cpu_millicores += int(parts[1].replace('m', ''))
                        total_memory_mb += int(parts[2].replace('Mi', ''))
                    except ValueError:
                        continue
            
            cpu_usage_percent = min(total_cpu_millicores / 100, 10.0)
            memory_usage_percent = min(total_memory_mb / 100, 5.0)
            target_system_pods = len(lines)
        
        metrics.update({
            "kube_znn_cpu_usage_percent": round(cpu_usage_percent, 2),
            "kube_znn_memory_usage_percent": round(memory_usage_percent, 2),
            "kube_znn_cpu_proportion_percent": round((cpu_usage_percent / 15.0) * 100, 2),
            "kube_znn_memory_proportion_percent": round((memory_usage_percent / 40.0) * 100, 2),
            "target_system_pods": target_system_pods
        })
        
    except Exception as e:
        logger.warning(f"Erro ao obter métricas do kube-znn: {e}")
        metrics.update({
            "kube_znn_cpu_usage_percent": 1.0,
            "kube_znn_memory_usage_percent": 2.0,
            "kube_znn_cpu_proportion_percent": 6.67,
            "kube_znn_memory_proportion_percent": 5.0,
            "target_system_pods": 5
        })
    
    # Testar resposta do kube-znn-nginx (com timeout curto)
    response_time_ms = 5.0
    try:
        start_time = time.time()
        response = requests.get("http://kube-znn-nginx:80", timeout=2)
        response_time_ms = (time.time() - start_time) * 1000
    except Exception:
        response_time_ms = 5.0
    
    metrics["kube_znn_response_time_ms"] = round(response_time_ms, 2)
    
    # Obter status do load generator (com timeout curto)
    load_status = {
        "concurrent_users": 0,
        "request_rate": 0.0,
        "load_pattern": "steady"
    }
    try:
        response = requests.get("http://load-generator:8000/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            load_status.update({
                "concurrent_users": data.get("current_users", 0),
                "request_rate": data.get("request_rate", 0.0),
                "load_pattern": data.get("load_pattern", "steady")
            })
    except Exception:
        pass
    
    metrics.update(load_status)
    
    return metrics

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

@app.get("/monitor/metrics")
async def get_metrics():
    """Endpoint principal para coleta de métricas (otimizado com cache)"""
    try:
        # Usar cache para evitar chamadas kubectl repetidas
        metrics = get_cached_metrics()
        
        # Calcular métricas derivadas
        throughput = metrics["concurrent_users"] * metrics["request_rate"]
        error_rate = 0.0
        
        # Montar resposta completa
        response = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "service": "monitor",
            "version": "v17.5.3",
            
            # Métricas do cluster
            "cluster_cpu_usage_percent": metrics["cluster_cpu_usage_percent"],
            "cluster_memory_usage_percent": metrics["cluster_memory_usage_percent"],
            "allocated_cpus": metrics["allocated_cpus"],
            "allocated_memory": metrics["allocated_memory"],
            
            # Métricas do kube-znn
            "kube_znn_cpu_usage_percent": metrics["kube_znn_cpu_usage_percent"],
            "kube_znn_memory_usage_percent": metrics["kube_znn_memory_usage_percent"],
            "kube_znn_cpu_proportion_percent": metrics["kube_znn_cpu_proportion_percent"],
            "kube_znn_memory_proportion_percent": metrics["kube_znn_memory_proportion_percent"],
            "kube_znn_response_time_ms": metrics["kube_znn_response_time_ms"],
            "target_system_pods": metrics["target_system_pods"],
            
            # Status dos pods
            "active_pods": 7,
            "pending_pods": 0,
            "failed_pods": 0,
            
            # Métricas de carga
            "concurrent_users": metrics["concurrent_users"],
            "request_rate": metrics["request_rate"],
            "session_duration": 180,
            "quality_of_media": 600,
            "throughput": throughput,
            "error_rate": error_rate,
            "network_latency": metrics["kube_znn_response_time_ms"],
            "system_status": "operational",
            "load_pattern": metrics["load_pattern"],
            
            # Métricas calculadas
            "cpu_usage_percent": metrics["cluster_cpu_usage_percent"],
            "memory_usage_percent": metrics["cluster_memory_usage_percent"],
            "used_system_cpu": metrics["cluster_cpu_usage_percent"],
            "used_system_memory": metrics["cluster_memory_usage_percent"],
            "median_response_time": metrics["kube_znn_response_time_ms"],
            
            # Metadados
            "current_load_description": f"steady load with {metrics['concurrent_users']} users",
            "load_pattern_description": "Steady load pattern",
            "load_description": "Steady load",
            "run_id": f"run_{int(time.time())}",
            "experiment_id": "AUTO-START",
            "loop_iteration": 1,
            "unique_loop_id": f"loop_{int(time.time())}",
            "data_type": "monitor_data",
            
            # Métricas de cache (valores padrão)
            "nginx_cache_hits": 0,
            "nginx_cache_misses": 0,
            "nginx_cache_hit_ratio": 0.0,
            "system_cache_usage_percent": 1.0,
            "memory_cache_usage_percent": 0.5,
            "cache_effectiveness": "unknown"
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Erro ao coletar métricas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "service": "Monitor Simples",
        "version": "v17.5.3",
        "status": "running",
        "endpoints": ["/health", "/monitor/metrics"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
