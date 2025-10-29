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

app = FastAPI(title="Monitor Simples", version="v17.5.1")

def get_cluster_resources() -> Dict[str, float]:
    """Coleta recursos básicos do cluster"""
    try:
        # Obter recursos do cluster via kubectl top nodes
        result = subprocess.run(
            ["kubectl", "top", "nodes", "--no-headers"],
            capture_output=True, text=True, timeout=15
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            total_cpu_millicores = 0
            total_memory_bytes = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    cpu_str = parts[1].replace('m', '')
                    memory_str = parts[2].replace('Mi', '')
                    try:
                        total_cpu_millicores += int(cpu_str)
                        total_memory_bytes += int(memory_str) * 1024 * 1024
                    except ValueError:
                        continue
            
            # Assumir cluster com 4 CPUs e 3919GB RAM
            total_cpu_cores = 4
            total_memory_gb = 3919
            
            cpu_usage_percent = min((total_cpu_millicores / (total_cpu_cores * 1000)) * 100, 100)
            memory_usage_percent = min((total_memory_bytes / (total_memory_gb * 1024**3)) * 100, 100)
            
            return {
                "cluster_cpu_usage_percent": round(cpu_usage_percent, 1),
                "cluster_memory_usage_percent": round(memory_usage_percent, 1),
                "allocated_cpus": total_cpu_cores,
                "allocated_memory": total_memory_gb
            }
        else:
            # Valores padrão se não conseguir obter métricas
            return {
                "cluster_cpu_usage_percent": 15.0,
                "cluster_memory_usage_percent": 40.0,
                "allocated_cpus": 4,
                "allocated_memory": 3919
            }
            
    except Exception as e:
        logger.warning(f"Erro ao obter recursos do cluster: {e}")
        return {
            "cluster_cpu_usage_percent": 15.0,
            "cluster_memory_usage_percent": 40.0,
            "allocated_cpus": 4,
            "allocated_memory": 3919
        }

def get_kube_znn_metrics() -> Dict[str, Any]:
    """Coleta métricas do kube-znn-nginx"""
    try:
        # Obter pods do kube-znn-nginx
        result = subprocess.run(
            ["kubectl", "get", "pods", "-l", "app=kube-znn-nginx", "--no-headers"],
            capture_output=True, text=True, timeout=15
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            kube_znn_pods = [line for line in lines if 'kube-znn-nginx' in line]
            target_system_pods = len(kube_znn_pods)
        else:
            target_system_pods = 5  # Valor padrão
        
        # Obter métricas de CPU/Memory dos pods
        cpu_usage_percent = 1.0
        memory_usage_percent = 2.0
        
        try:
            result = subprocess.run(
                ["kubectl", "top", "pods", "-l", "app=kube-znn-nginx", "--no-headers"],
                capture_output=True, text=True, timeout=15
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
                
                cpu_usage_percent = min(total_cpu_millicores / 100, 10.0)  # Máximo 10%
                memory_usage_percent = min(total_memory_mb / 100, 5.0)     # Máximo 5%
        except Exception:
            pass
        
        # Testar resposta do kube-znn-nginx
        response_time_ms = 5.0
        try:
            start_time = time.time()
            response = requests.get("http://kube-znn-nginx:80", timeout=5)
            response_time_ms = (time.time() - start_time) * 1000
        except Exception:
            response_time_ms = 5.0
        
        return {
            "kube_znn_cpu_usage_percent": round(cpu_usage_percent, 2),
            "kube_znn_memory_usage_percent": round(memory_usage_percent, 2),
            "kube_znn_cpu_proportion_percent": round((cpu_usage_percent / 15.0) * 100, 2),
            "kube_znn_memory_proportion_percent": round((memory_usage_percent / 40.0) * 100, 2),
            "kube_znn_response_time_ms": round(response_time_ms, 2),
            "target_system_pods": target_system_pods
        }
        
    except Exception as e:
        logger.warning(f"Erro ao obter métricas do kube-znn: {e}")
        return {
            "kube_znn_cpu_usage_percent": 1.0,
            "kube_znn_memory_usage_percent": 2.0,
            "kube_znn_cpu_proportion_percent": 6.67,
            "kube_znn_memory_proportion_percent": 5.0,
            "kube_znn_response_time_ms": 5.0,
            "target_system_pods": 5
        }

def get_load_generator_status() -> Dict[str, Any]:
    """Obtém status do load generator"""
    try:
        response = requests.get("http://load-generator:8000/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "concurrent_users": data.get("current_users", 0),
                "request_rate": data.get("request_rate", 0.0),
                "load_pattern": data.get("load_pattern", "steady")
            }
    except Exception:
        pass
    
    return {
        "concurrent_users": 0,
        "request_rate": 0.0,
        "load_pattern": "steady"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

@app.get("/monitor/metrics")
async def get_metrics():
    """Endpoint principal para coleta de métricas"""
    try:
        # Coletar métricas básicas
        cluster_metrics = get_cluster_resources()
        kube_znn_metrics = get_kube_znn_metrics()
        load_status = get_load_generator_status()
        
        # Calcular métricas derivadas
        throughput = load_status["concurrent_users"] * load_status["request_rate"]
        error_rate = 0.0  # Assumir zero erros por enquanto
        
        # Montar resposta completa
        metrics = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "service": "monitor",
            "version": "v17.5.1",
            
            # Métricas do cluster
            **cluster_metrics,
            
            # Métricas do kube-znn
            **kube_znn_metrics,
            
            # Status dos pods
            "active_pods": 7,  # Valor fixo baseado no cluster atual
            "pending_pods": 0,
            "failed_pods": 0,
            
            # Métricas de carga
            **load_status,
            "session_duration": 180,
            "quality_of_media": 600,
            "throughput": throughput,
            "error_rate": error_rate,
            "network_latency": kube_znn_metrics["kube_znn_response_time_ms"],
            "system_status": "operational",
            
            # Métricas calculadas
            "cpu_usage_percent": cluster_metrics["cluster_cpu_usage_percent"],
            "memory_usage_percent": cluster_metrics["cluster_memory_usage_percent"],
            "used_system_cpu": cluster_metrics["cluster_cpu_usage_percent"],
            "used_system_memory": cluster_metrics["cluster_memory_usage_percent"],
            "median_response_time": kube_znn_metrics["kube_znn_response_time_ms"],
            
            # Metadados
            "current_load_description": f"steady load with {load_status['concurrent_users']} users",
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
        
        return metrics
        
    except Exception as e:
        logger.error(f"Erro ao coletar métricas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "service": "Monitor Simples",
        "version": "v17.5.1",
        "status": "running",
        "endpoints": ["/health", "/monitor/metrics"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
