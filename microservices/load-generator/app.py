#!/usr/bin/env python3
"""
Load Generator Service - V2.0 - CORRIGIDO
Microserviço para simular carga REAL de usuários e gerar métricas de carga
Fornece dados de carga para o Monitor Service
"""

import json
import logging
import os
import random
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Load Generator Service", version="v17.8.3")

class LoadPattern:
    """Padrões de carga disponíveis"""
    STEADY = "steady"
    BURST = "burst"
    GRADUAL = "gradual"
    SPIKY = "spiky"

class LoadConfiguration(BaseModel):
    """Modelo para configuração de carga"""
    concurrent_users: int
    request_rate: float
    load_pattern: str = LoadPattern.STEADY
    session_duration: int = 180

class LoadGenerator:
    """Gerador de carga de usuários - VERSÃO CORRIGIDA"""
    
    def __init__(self):
        self.current_users = int(os.getenv('LOAD_GENERATOR_CONCURRENT_USERS', 25))
        self.request_rate = float(os.getenv('LOAD_GENERATOR_REQUEST_RATE', 2.5))
        self.session_duration = int(os.getenv('LOAD_GENERATOR_SESSION_DURATION', 180))
        self.load_pattern = os.getenv('LOAD_GENERATOR_LOAD_PATTERN', LoadPattern.STEADY)
        self.is_running = False
        self.load_thread = None
        self.metrics_history = []
        self._api_configured = False
        self._request_count = 0
        self._error_count = 0
        self._start_time = None
        
    def start_load_generation(self):
        """Inicia a geração de carga"""
        if self.is_running:
            logger.warning("Load generation já está rodando")
            return
        
        self.is_running = True
        self._start_time = time.time()
        self._request_count = 0
        self._error_count = 0
        self.load_thread = threading.Thread(target=self._generate_load, daemon=True)
        self.load_thread.start()
        logger.info(f"Load generation iniciado com padrão {self.load_pattern}")
    
    def stop_load_generation(self):
        """Para a geração de carga"""
        self.is_running = False
        if self.load_thread:
            self.load_thread.join(timeout=5)
        logger.info("Load generation parado")
    
    def _generate_load(self):
        """Gera carga continuamente - VERSÃO CORRIGIDA"""
        while self.is_running:
            try:
                # Atualizar métricas baseadas no padrão de carga
                self._update_metrics()
                
                # Simular requisições REAIS para kube-znn
                self._simulate_real_requests()
                
                # Aguardar próxima iteração
                time.sleep(1)  # Reduzir para 1 segundo para maior precisão
                
            except Exception as e:
                logger.error(f"Erro na geração de carga: {e}")
                time.sleep(5)
    
    def _update_metrics(self):
        """Atualiza métricas baseadas no padrão de carga"""
        current_time = datetime.now()
        
        # CORREÇÃO: Usar valores configurados via API, não variáveis de ambiente
        # Apenas usar variáveis de ambiente como fallback se não foi configurado via API
        if not self._api_configured:
            base_users = int(os.getenv('LOAD_GENERATOR_CONCURRENT_USERS', 25))
            base_rate = float(os.getenv('LOAD_GENERATOR_REQUEST_RATE', 2.5))
        else:
            # Usar valores já configurados via API
            base_users = self.current_users
            base_rate = self.request_rate
        
        if self.load_pattern == LoadPattern.STEADY:
            # Carga constante - manter valores configurados via API
            pass  # Manter self.current_users e self.request_rate como estão
            
        elif self.load_pattern == LoadPattern.BURST:
            # Carga em rajadas - usar valores configurados via API
            minute = current_time.minute
            if minute % 5 < 2:  # Rajada a cada 5 minutos por 2 minutos
                self.current_users = base_users * 2
                self.request_rate = base_rate * 1.5
            else:
                self.current_users = base_users
                self.request_rate = base_rate
                
        elif self.load_pattern == LoadPattern.GRADUAL:
            # Carga gradual crescente - APENAS se não foi configurado via API
            if not self._api_configured:
                hour = current_time.hour
                multiplier = 1 + (hour % 8) * 0.2  # Cresce gradualmente ao longo do dia
                self.current_users = int(base_users * multiplier)
                self.request_rate = base_rate * multiplier
            
        elif self.load_pattern == LoadPattern.SPIKY:
            # Carga com picos aleatórios
            if random.random() < 0.1:  # 10% de chance de pico
                self.current_users = base_users * 3
                self.request_rate = base_rate * 2
            else:
                self.current_users = base_users
                self.request_rate = base_rate
        
        # Adicionar variação aleatória apenas se não foi configurado via API
        if not self._api_configured:
            self.current_users = max(1, self.current_users + random.randint(-5, 5))
            self.request_rate = max(0.1, self.request_rate + random.uniform(-0.5, 0.5))
    
    def _simulate_real_requests(self):
        """Simula requisições REAIS para o kube-znn - VERSÃO CORRIGIDA"""
        try:
            # Calcular número REAL de requisições baseado na taxa configurada
            # request_rate é a taxa TOTAL de requisições por segundo
            requests_per_second = int(self.request_rate)
            
            # Para evitar sobrecarga extrema, limitar mas permitir carga significativa
            if requests_per_second > 1000:
                # Para cargas muito altas, fazer requisições em lotes
                batch_size = min(100, requests_per_second // 10)
                num_batches = requests_per_second // batch_size
                
                logger.info(f"Simulando {requests_per_second} req/s ({num_batches} lotes de {batch_size}) para {self.current_users} usuários")
                
                # Fazer requisições em lotes para evitar bloqueio
                for batch in range(num_batches):
                    if not self.is_running:
                        break
                    
                    # Fazer lote de requisições
                    for req_num in range(batch_size):
                        try:
                            # Cache busting: adicionar parâmetros únicos para evitar cache
                            cache_buster = f"?t={int(time.time() * 1000)}&r={req_num}&u={self.current_users}&b={batch}"
                            url = f"http://kube-znn-nginx:80/{cache_buster}"
                            
                            # Headers para evitar cache
                            headers = {
                                'Cache-Control': 'no-cache, no-store, must-revalidate',
                                'Pragma': 'no-cache',
                                'Expires': '0',
                                'User-Agent': f'LoadGenerator-{self.current_users}users-{req_num}'
                            }
                            
                            response = requests.get(url, timeout=0.5, headers=headers)
                            self._request_count += 1
                            if response.status_code != 200:
                                self._error_count += 1
                        except Exception as e:
                            self._error_count += 1
                            logger.debug(f"Erro na requisição: {e}")
                    
                    # Pequena pausa entre lotes para não sobrecarregar
                    time.sleep(0.01)
            else:
                # Para cargas menores, fazer todas as requisições
                logger.info(f"Simulando {requests_per_second} req/s para {self.current_users} usuários")
                
                for req_num in range(requests_per_second):
                    if not self.is_running:
                        break
                    
                    try:
                        # Cache busting: adicionar parâmetros únicos para evitar cache
                        cache_buster = f"?t={int(time.time() * 1000)}&r={req_num}&u={self.current_users}"
                        url = f"http://kube-znn-nginx:80/{cache_buster}"
                        
                        # Headers para evitar cache
                        headers = {
                            'Cache-Control': 'no-cache, no-store, must-revalidate',
                            'Pragma': 'no-cache',
                            'Expires': '0',
                            'User-Agent': f'LoadGenerator-{self.current_users}users-{req_num}'
                        }
                        
                        response = requests.get(url, timeout=0.5, headers=headers)
                        self._request_count += 1
                        if response.status_code != 200:
                            self._error_count += 1
                    except Exception as e:
                        self._error_count += 1
                        logger.debug(f"Erro na requisição: {e}")
                    
                    # Pequena pausa para distribuir as requisições ao longo do segundo
                    if requests_per_second > 10:
                        time.sleep(1.0 / requests_per_second)
                        
        except Exception as e:
            logger.error(f"Erro ao simular requisições: {e}")
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Retorna métricas atuais"""
        current_time = time.time()
        elapsed_time = current_time - self._start_time if self._start_time else 0
        
        # Calcular taxa de erro
        error_rate = (self._error_count / max(self._request_count, 1)) * 100
        
        # Calcular throughput real
        real_throughput = self._request_count / max(elapsed_time, 1)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "concurrent_users": self.current_users,
            "request_rate": round(self.request_rate, 2),
            "session_duration": self.session_duration,
            "load_pattern": self.load_pattern,
            "load_pattern_description": self._get_pattern_description(),
            "load_description": self._get_load_description(),
            "is_running": self.is_running,
            "real_metrics": {
                "total_requests": self._request_count,
                "total_errors": self._error_count,
                "error_rate_percent": round(error_rate, 2),
                "real_throughput_rps": round(real_throughput, 2),
                "elapsed_time_seconds": round(elapsed_time, 2)
            }
        }
    
    def _get_pattern_description(self) -> str:
        """Retorna descrição do padrão de carga"""
        descriptions = {
            LoadPattern.STEADY: "Steady load pattern - constant user load",
            LoadPattern.BURST: "Burst load pattern - periodic load spikes",
            LoadPattern.GRADUAL: "Gradual load pattern - slowly increasing load",
            LoadPattern.SPIKY: "Spiky load pattern - random load spikes"
        }
        return descriptions.get(self.load_pattern, "Unknown pattern")
    
    def _get_load_description(self) -> str:
        """Retorna descrição da carga atual"""
        if self.current_users < 20:
            return "Light load"
        elif self.current_users < 50:
            return "Moderate load"
        elif self.current_users < 100:
            return "Heavy load"
        else:
            return "Very heavy load"
    
    def set_load_pattern(self, pattern: str):
        """Define o padrão de carga"""
        if pattern in [LoadPattern.STEADY, LoadPattern.BURST, LoadPattern.GRADUAL, LoadPattern.SPIKY]:
            self.load_pattern = pattern
            logger.info(f"Load pattern alterado para {pattern}")
        else:
            raise ValueError(f"Padrão de carga inválido: {pattern}")
    
    def set_concurrent_users(self, users: int):
        """Define número de usuários concorrentes"""
        self.current_users = max(1, users)
        self._api_configured = True  # Marcar como configurado via API
        logger.info(f"Concurrent users alterado para {self.current_users}")
    
    def set_request_rate(self, rate: float):
        """Define taxa de requisições"""
        self.request_rate = max(0.1, rate)
        self._api_configured = True  # Marcar como configurado via API
        logger.info(f"Request rate alterado para {self.request_rate}")
    
    def set_session_duration(self, duration: int):
        """Define duração da sessão"""
        self.session_duration = max(60, duration)
        logger.info(f"Session duration alterado para {self.session_duration}")

# Instanciar o gerador de carga
load_generator = LoadGenerator()

@app.on_event("startup")
async def startup_event():
    """Evento de inicialização"""
    logger.info("Iniciando Load Generator Service...")
    load_generator.start_load_generation()

@app.on_event("shutdown")
async def shutdown_event():
    """Evento de desligamento"""
    logger.info("Parando Load Generator Service...")
    load_generator.stop_load_generation()

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "service": "Load Generator Service",
        "version": "v17.8.1",
        "status": "running",
        "description": "Serviço para simular carga real de usuários"
    }

@app.get("/metrics")
async def get_metrics():
    """Retorna métricas atuais"""
    return load_generator.get_current_metrics()

@app.post("/configure")
async def configure_load(config: LoadConfiguration):
    """Configura parâmetros de carga"""
    try:
        load_generator.set_concurrent_users(config.concurrent_users)
        load_generator.set_request_rate(config.request_rate)
        load_generator.set_load_pattern(config.load_pattern)
        load_generator.set_session_duration(config.session_duration)
        
        return {
            "status": "success",
            "message": "Configuração de carga atualizada",
            "current_metrics": load_generator.get_current_metrics()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/start")
async def start_load():
    """Inicia geração de carga"""
    try:
        load_generator.start_load_generation()
        return {
            "status": "success",
            "message": "Load generation iniciado",
            "current_metrics": load_generator.get_current_metrics()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/stop")
async def stop_load():
    """Para geração de carga"""
    try:
        load_generator.stop_load_generation()
        return {
            "status": "success",
            "message": "Load generation parado",
            "current_metrics": load_generator.get_current_metrics()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/status")
async def get_status():
    """Retorna status do serviço"""
    return {
        "service": "Load Generator Service",
        "version": "v17.8.1",
        "is_running": load_generator.is_running,
        "current_users": load_generator.current_users,
        "request_rate": load_generator.request_rate,
        "load_pattern": load_generator.load_pattern
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)