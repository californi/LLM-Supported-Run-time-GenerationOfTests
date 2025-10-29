#!/usr/bin/env python3
"""
Microserviço Analyzer Simplificado - V10.2
Versão simplificada que funciona sem erros de sintaxe
"""

import requests
import json
import logging
import os
import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
from functools import wraps
# Retry decorator for network operations
def retry_on_failure(max_retries=3, backoff_factor=1, timeout_increment=30):
    """Decorator para retry automático com backoff exponencial"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    # Aumentar timeout progressivamente
                    if 'timeout' in kwargs:
                        kwargs['timeout'] += attempt * timeout_increment
                    
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"Retry successful on attempt {attempt + 1}")
                    return result
                    
                except (requests.exceptions.Timeout, 
                       requests.exceptions.ConnectionError,
                       requests.exceptions.ReadTimeout) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries} attempts failed. Last error: {e}")
                        
            raise last_exception
        return wrapper
    return decorator

# Data Collector integrado
import json
import logging
import os
import redis
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class MessageType(Enum):
    """Message types in the MAPEK system"""
    MONITOR_TO_KNOWLEDGE = "monitor_to_knowledge"
    MONITOR_TO_ANALYZER = "monitor_to_analyzer"
    ANALYZER_TO_KNOWLEDGE = "analyzer_to_knowledge"
    ANALYZER_TO_LLM = "analyzer_to_llm"
    LLM_TO_ANALYZER = "llm_to_analyzer"
    ANALYZER_TO_PLANNER = "analyzer_to_planner"

class DataType(Enum):
    """Types of collected data"""
    MESSAGE = "message"
    TEMPLATE = "template"
    PROMPT = "prompt"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"

@dataclass
class DataCollectionEntry:
    """Structure for data collection entry"""
    experiment_id: str
    timestamp: str
    data_type: str
    message_type: Optional[str]
    source_service: str
    target_service: Optional[str]
    data: Dict[str, Any]
    metadata: Dict[str, Any]

class DataCollector:
    """Centralized MAPEK data collection system"""
    
    def __init__(self, experiment_id: str = None):
        self.experiment_id = experiment_id or os.getenv('EXPERIMENT_ID', 'UNKNOWN')
        
        # Handle Redis URL format from Kubernetes
        redis_port = os.getenv('REDIS_PORT', '6379')
        if '://' in redis_port:
            redis_port = redis_port.split(':')[-1]
        
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(redis_port),
            decode_responses=True
        )
        self.knowledge_url = os.getenv('KNOWLEDGE_URL', 'http://knowledge:8000')
        
    def collect_template(
        self,
        service_name: str,
        template_name: str,
        template_content: str,
        variables: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> str:
        """Collects template with used variables"""
        entry = DataCollectionEntry(
            experiment_id=self.experiment_id,
            timestamp=datetime.now().isoformat(),
            data_type=DataType.TEMPLATE.value,
            message_type=None,
            source_service=service_name,
            target_service=None,
            data={
                "template_name": template_name,
                "template_content": template_content,
                "variables": variables,
                "filled_template": template_content.format(**variables) if variables else template_content
            },
            metadata=metadata or {}
        )
        
        return self._store_entry(entry)
    
    def collect_llm_interaction(
        self,
        service_name: str,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> str:
        """Collects complete interaction with LLM-service"""
        entry = DataCollectionEntry(
            experiment_id=self.experiment_id,
            timestamp=datetime.now().isoformat(),
            data_type=DataType.LLM_REQUEST.value,
            message_type=None,
            source_service=service_name,
            target_service="llm-service",
            data={
                "request": request_data,
                "response": response_data,
                "interaction_complete": True
            },
            metadata=metadata or {}
        )
        
        return self._store_entry(entry)
    
    def _store_entry(self, entry: DataCollectionEntry) -> str:
        """Stores entry in Redis and Knowledge Service"""
        try:
            # Gerar ID único
            entry_id = f"{entry.data_type}_{entry.experiment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Converter para dict
            entry_dict = asdict(entry)
            entry_dict['entry_id'] = entry_id
            
            # Armazenar no Redis
            redis_key = f"data_collection:{entry_id}"
            self.redis_client.setex(redis_key, 86400, json.dumps(entry_dict))  # Expira em 24h
            
            # Adicionar à lista do experimento
            experiment_list_key = f"experiment_data:{self.experiment_id}"
            self.redis_client.lpush(experiment_list_key, entry_id)
            
            # Enviar para Knowledge Service
            try:
                knowledge_data = {
                    "experiment_id": entry.experiment_id,
                    "run_id": entry.metadata.get("run_id", "unknown"),
                    "timestamp": entry.timestamp,
                    "data_type": entry.data_type,
                    "message_type": entry.message_type,
                    "source_service": entry.source_service,
                    "target_service": entry.target_service,
                    "data": entry.data,
                    "metadata": entry.metadata,
                    "entry_id": entry_id
                }
                
                knowledge_response = requests.post(
                    f"{self.knowledge_url}/data-collection",
                    json=knowledge_data,
                    timeout=10
                )
                
                if knowledge_response.status_code == 200:
                    logger.info(f"Dados coletados enviados para Knowledge: {entry_id}")
                else:
                    logger.warning(f"Falha ao enviar para Knowledge: {knowledge_response.status_code}")
                    
            except Exception as knowledge_error:
                logger.warning(f"Erro ao enviar para Knowledge: {knowledge_error}")
            
            logger.info(f"Dados coletados: {entry_id} - {entry.data_type} de {entry.source_service}")
            return entry_id
            
        except Exception as e:
            logger.error(f"Error storing collected data: {e}")
            return ""

def get_data_collector(experiment_id: str = None) -> DataCollector:
    """Obtém instância do coletor de dados"""
    return DataCollector(experiment_id)

class AnalyzerLogger:
    """Sistema de logging detalhado para o Analyser"""
    
    def __init__(self, experiment_id: str, correlation_id: str = None):
        self.experiment_id = experiment_id
        self.correlation_id = correlation_id or f"corr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_dir = f"/app/logs/analyzer"
        os.makedirs(self.log_dir, exist_ok=True)
        
    def log_execution_start(self, request_data: Dict[str, Any]):
        """Log do início da execução do Analyser"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "correlation_id": self.correlation_id,
            "service": "analyzer",
            "action": "execution_start",
            "request_data": request_data,
            "metrics_received": {
                "cpu_usage_percent": request_data.get("cpu_usage_percent"),
                "memory_usage_percent": request_data.get("memory_usage_percent"),
                "kube_znn_response_time_ms": request_data.get("kube_znn_response_time_ms"),
                "concurrent_users": request_data.get("concurrent_users"),
                "request_rate": request_data.get("request_rate")
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_execution_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer execution log saved: {log_file}")
        
    def log_knowledge_data_read(self, knowledge_data: Dict[str, Any]):
        """Log dos dados lidos do Knowledge Service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "knowledge_data_read",
            "source_service": "knowledge",
            "knowledge_data": knowledge_data,
            "data_summary": {
                "cpu_usage_percent": knowledge_data.get("cpu_usage_percent"),
                "memory_usage_percent": knowledge_data.get("memory_usage_percent"),
                "kube_znn_response_time_ms": knowledge_data.get("kube_znn_response_time_ms"),
                "concurrent_users": knowledge_data.get("concurrent_users"),
                "request_rate": knowledge_data.get("request_rate")
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_knowledge_read_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer knowledge data read log saved: {log_file}")
        
    def log_template_generation(self, template_content: str, template_context: Dict[str, Any], filled_prompt: str):
        """Log of template and prompt generation"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "template_generation",
            "template_content": template_content,
            "template_context": template_context,
            "filled_prompt": filled_prompt,
            "template_version": "v10.3",
            "prompt_length": len(filled_prompt)
        }
        
        log_file = f"{self.log_dir}/analyzer_template_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer template generation log saved: {log_file}")
        
    def log_llm_request(self, llm_request_data: Dict[str, Any]):
        """Log of the request sent to the LLM-service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "llm_request",
            "target_service": "llm-service",
            "llm_request_data": llm_request_data,
            "request_summary": {
                "prompt_type": llm_request_data.get("prompt_type"),
                "category": llm_request_data.get("category"),
                "prompt_length": len(llm_request_data.get("prompt", "")),
                "context_keys": list(llm_request_data.get("context", {}).keys())
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_llm_request_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer LLM request log saved: {log_file}")
        
    def log_llm_response(self, llm_response_data: Dict[str, Any], llm_analysis: str):
        """Log da resposta recebida do LLM-service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "llm_response",
            "source_service": "llm-service",
            "llm_response_data": llm_response_data,
            "llm_analysis": llm_analysis,
            "response_summary": {
                "response_length": len(str(llm_analysis)),
                "is_json": self._is_valid_json(str(llm_analysis)),
                "contains_recommendation": "recommended_test_type" in str(llm_analysis),
                "contains_justification": "justification" in str(llm_analysis)
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_llm_response_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer LLM response log saved: {log_file}")
        
    def log_planner_notification(self, planner_url: str, notification_data: Dict[str, Any], response_status: int = None, response_data: Any = None):
        """Log da notificação enviada ao Planner"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "planner_notification",
            "target_service": "planner",
            "planner_url": planner_url,
            "notification_data": notification_data,
            "response_status": response_status,
            "response_data": response_data,
            "success": response_status == 200 if response_status else None,
            "notification_summary": {
                "recommended_test_type": notification_data.get("recommended_test_type"),
                "test_justification": notification_data.get("test_justification"),
                "test_priority": notification_data.get("test_priority"),
                "health_criterion": notification_data.get("health_criterion")
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_planner_notification_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer planner notification log saved: {log_file}")
        
    def log_knowledge_storage(self, knowledge_data: Dict[str, Any], storage_success: bool):
        """Log do armazenamento de dados no Knowledge"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "knowledge_storage",
            "target_service": "knowledge",
            "knowledge_data": knowledge_data,
            "storage_success": storage_success,
            "storage_summary": {
                "analysis_keys": list(knowledge_data.get("analysis_result", {}).keys()) if knowledge_data.get("analysis_result") else [],
                "source": knowledge_data.get("source"),
                "timestamp": knowledge_data.get("timestamp")
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_knowledge_storage_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer knowledge storage log saved: {log_file}")
        
    def log_execution_complete(self, final_result: Dict[str, Any]):
        """Log da conclusão da execução do Analyser"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "service": "analyzer",
            "action": "execution_complete",
            "final_result": final_result,
            "execution_summary": {
                "health_criterion": final_result.get("health_criterion"),
                "recommended_test_type": final_result.get("recommended_test_type"),
                "test_justification": final_result.get("test_justification"),
                "test_priority": final_result.get("test_priority"),
                "llm_enhanced": final_result.get("llm_enhanced"),
                "template_applied": final_result.get("template_v10_3_applied")
            }
        }
        
        log_file = f"{self.log_dir}/analyzer_complete_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Analyzer execution complete log saved: {log_file}")
        
    def _is_valid_json(self, text: str) -> bool:
        """Verifies if the text is valid JSON"""
        try:
            json.loads(text)
            return True
        except:
            return False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instanciar logger global
analyzer_logger = None

app = FastAPI(title="Analyzer Service", version="v16.7.8")

# Service URLs
KNOWLEDGE_URL = os.getenv('KNOWLEDGE_URL', 'http://knowledge:8000')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')

# Redis client
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# Configurações de análise
ANALYZER_INTERVAL = int(os.getenv('ANALYZER_INTERVAL', '60'))  # segundos

class AnalysisRequest(BaseModel):
    """Request para análise do sistema"""
    experiment_id: str
    run_id: str = "unknown"
    correlation_id: str = "unknown"
    cpu_usage_percent: float
    memory_usage_percent: float
    kube_znn_response_time_ms: float
    error_rate: float
    throughput: float
    network_latency: float
    quality_of_media: int = 600
    concurrent_users: int = 30
    request_rate: float = 3.0
    session_duration: int = 120
    load_pattern: str = "burst"
    load_pattern_description: str = "Burst load pattern"
    load_description: str = "Moderate load"
    target_system_pods: int = 3
    active_pods: int = 3
    pending_pods: int = 0
    failed_pods: int = 0
    allocated_cpus: int = 6
    allocated_memory: int = 6

class AnalysisResponse(BaseModel):
    """Response da análise"""
    experiment_id: str
    health_criterion: str
    cpu_range_description: str
    memory_range_description: str
    response_time_range_description: str
    analysis_timestamp: str
    template_v10_3_applied: bool
    template_v10_3_prompt: str
    llm_analysis: str
    llm_enhanced: bool
    recommended_test_type: str
    test_justification: str
    test_priority: str
    cpu_usage_percent: float
    memory_usage_percent: float
    kube_znn_response_time_ms: float

class AnalyzerTemplate:
    def __init__(self):
        self.template_version = "v16.7.8"
        self.target_system = "Kube-znn"
        self.system_type = "streaming de media"
        self.data_collector = get_data_collector()
        
    def get_analyzer_template(self) -> str:
        return """Analyze kube-znn service metrics and recommend test type.

METRICS:
- CPU: {used_system_cpu}% ({cpu_range_description})
- Memory: {used_system_memory}% ({memory_range_description})  
- Response Time: {median_response_time}ms ({response_time_range_description})
- Error Rate: {error_rate}%
- Throughput: {throughput} req/s
- Network Latency: {network_latency}ms

LOAD:
- Users: {concurrent_users}, Rate: {request_rate} req/s, Duration: {session_duration}s
- Pattern: {load_pattern} ({load_pattern_description})
- Current: {current_load_description}

INFRASTRUCTURE:
- Pods: {active_pods} active, {pending_pods} pending, {failed_pods} failed
- Resources: {allocated_cpus} CPUs, {allocated_memory}GB RAM
- Target: {target_system_pods} pods, Quality: {quality_of_media}

ADDITIONAL CONTEXT:
- Pod Status: {active_pods} running, {pending_pods} pending, {failed_pods} failed
- Resource Allocation: {allocated_cpus} CPUs, {allocated_memory}GB RAM allocated
- Load Pattern: {load_pattern} with {concurrent_users} users at {request_rate} req/s
- System Health: {health_criterion} (CPU: {used_system_cpu}%, Memory: {used_system_memory}%, Response: {median_response_time}ms)

STATUS: {system_status}

ANALYSIS: Analyze ALL metrics to recommend the most appropriate test type.

TEST TYPE SELECTION RULES (HOLISTIC ANALYSIS):
Analyze ALL metrics together to determine the PRIMARY concern. Use this DECISION TREE:

PRIORITY 1 - REACHABILITY:
- Choose "reachability" when connectivity is the main issue
- Conditions: Many failed pods (>5) + high error rate (>50%) + few users connecting (<10)
- Indicators: System cannot be reached, high network latency (>1000ms), pods not responding
- Example: Failed pods: 15, Error rate: 95%, Users: 1

PRIORITY 2 - LOAD (HIGHEST PRIORITY CHECK):
- Choose "load" when capacity/scalability is the main issue
- Conditions: High CPU/memory (>70%) + many users (>100) + high request rate (>50 req/s)
- KEY POINT: High response time with high CPU/memory + many users = LOAD, not response_time
- System is overloaded and struggling with demand
- Example: CPU: 83%, Memory: 82%, Users: 668, Request rate: 115 req/s

PRIORITY 3 - RESPONSE_TIME:
- Choose "response_time" when performance/latency is the main issue
- Conditions: High response time (>1000ms) + stable system + few users (<10)
- System works but is slow, NOT overloaded (CPU/memory <70%)
- ONLY if load conditions are NOT met
- Example: Response time: 5000ms, CPU: 20%, Memory: 25%, Users: 4

DECISION FLOW:
1. Check failed pods + error rate → reachability?
2. Check CPU/memory + users + request rate → load?
3. Else → response_time?

RESPONSE (JSON only):
{{
  "analysis_summary": {{
    "recommended_test_type": "reachability|response_time|load",
    "justification": "Detailed explanation of why this test type is most appropriate based on the metrics",
    "priority": "high|medium|low"
  }}
}}

Return only valid JSON."""

def get_range_description(value: float, thresholds: list, descriptions: list) -> str:
    """Retorna descrição do range baseado no valor e thresholds"""
    if value < thresholds[0]:
        return descriptions[0]
    elif value < thresholds[1]:
        return descriptions[1]
    else:
        return descriptions[2]

def get_health_criterion(cpu: float, memory: float, response_time: float) -> str:
    """Determina o critério de saúde baseado nas métricas"""
    if cpu < 25 and memory < 30 and response_time < 14:
        return "Healthy"
    elif cpu < 60 and memory < 70 and response_time < 70:
        return "Saturated"
    else:
        return "Critical"

def get_range_description(value: float, thresholds: list, descriptions: list) -> str:
    """Retorna descrição do range baseado no valor"""
    for i, threshold in enumerate(thresholds):
        if value < threshold:
            return descriptions[i]
    return descriptions[-1]

def determine_test_type_from_metrics(cpu_usage: float, memory_usage: float, response_time: float, error_rate: float = 0.0, failed_pods: int = 0, pending_pods: int = 0) -> Dict[str, str]:
    """Determine test type directly from metrics without LLM dependency - LLM should be primary recommender"""
    # Esta função é apenas um fallback quando o LLM falha
    # O LLM deve ser sempre o responsável pelas recomendações
    
    # Prioridade 1: Problemas de conectividade (mais crítico)
    if failed_pods > 0 or pending_pods > 0 or error_rate > 0:
        return {
            "test_type": "reachability",
            "justification": "Connectivity issues detected (failed/pending pods or errors), focus on reachability validation",
            "priority": "high"
        }
    
    # Prioridade 2: Problemas de performance (response time alto) - CORRIGIDO: maior prioridade
    elif response_time > 70:
        return {
            "test_type": "response_time",
            "justification": "High response time detected (>70ms), focus on performance optimization",
            "priority": "high"
        }
    
    # Prioridade 3: Problemas de capacidade (recursos altos)
    elif cpu_usage > 60 or memory_usage > 70:
        return {
            "test_type": "load",
            "justification": "High resource usage detected (CPU > 60% or Memory > 70%), evaluate capacity limits", 
            "priority": "medium"
        }
    
    # Prioridade 4: Sistema saudável, validar conectividade básica
    else:
        return {
            "test_type": "reachability",
            "justification": "System operating within healthy parameters, focus on baseline connectivity validation",
            "priority": "low"
        }

async def get_latest_monitoring_data() -> Dict[str, Any]:
    """Obtém os dados mais recentes do Knowledge Service"""
    try:
        # CORREÇÃO: Usar endpoint /data-collection em vez de /monitor-data
        knowledge_response = requests.get(f"{KNOWLEDGE_URL}/data-collection/LD-001", timeout=5)
        if knowledge_response.status_code == 200:
            data = knowledge_response.json()
            # CORREÇÃO: Pegar o ÚLTIMO item da lista (mais recente)
            if isinstance(data, list) and len(data) > 0:
                monitor_data = data[-1]  # Último item = mais recente
            else:
                monitor_data = {}
            
            return {
                # Métricas principais
                "cpu_usage_percent": monitor_data.get("cpu_usage_percent", 0.0),
                "memory_usage_percent": monitor_data.get("memory_usage_percent", 0.0),
                "kube_znn_response_time_ms": monitor_data.get("kube_znn_response_time_ms", 0.0),
                
                # Carga de requests
                "concurrent_users": monitor_data.get("concurrent_users", 0),
                "request_rate": monitor_data.get("request_rate", 0.0),
                "session_duration": monitor_data.get("session_duration", 120),
                "load_pattern": monitor_data.get("load_pattern", "burst"),
                "load_pattern_description": monitor_data.get("load_pattern_description", "Burst pattern"),
                "load_description": monitor_data.get("load_description", "Moderate load"),
                
                # Configuração do target system
                "target_system_pods": monitor_data.get("target_system_pods", int(os.getenv('TARGET_SYSTEM_REPLICAS', 3))),
                "quality_of_media": monitor_data.get("quality_of_media", int(os.getenv('TARGET_SYSTEM_QUALITY', 600))),
                
                # Configuração da infraestrutura
                "allocated_cpus": monitor_data.get("allocated_cpus", 6),
                "allocated_memory": monitor_data.get("allocated_memory", 6),
                
                # Estado operacional
                "error_rate": monitor_data.get("error_rate", 0.0),
                "throughput": monitor_data.get("throughput", 0.0),
                "network_latency": monitor_data.get("network_latency", 0.0),
                "active_pods": monitor_data.get("active_pods", 5),
                "pending_pods": monitor_data.get("pending_pods", 0),
                "failed_pods": monitor_data.get("failed_pods", 0),
                
                # Metadados
                "timestamp": monitor_data.get("timestamp", datetime.now().isoformat()),
                "experiment_id": monitor_data.get("experiment_id", "unknown"),
                "run_id": monitor_data.get("run_id", "unknown")
            }
        else:
            logger.warning(f"Falha ao buscar dados do Knowledge: {knowledge_response.status_code}")
            return get_default_monitoring_data()
    except Exception as e:
        logger.error(f"Erro ao obter dados de monitoramento: {e}")
        return get_default_monitoring_data()

def get_default_monitoring_data() -> Dict[str, Any]:
    """Retorna dados padrão quando não consegue obter do Knowledge"""
    return {
        "cpu_usage_percent": 0.0,
        "memory_usage_percent": 0.0,
        "kube_znn_response_time_ms": 0.0,
        "concurrent_users": 0,
        "request_rate": 0.0,
        "session_duration": 120,
        "load_pattern": "burst",
        "load_pattern_description": "Burst pattern",
        "load_description": "Moderate load",
        "target_system_pods": int(os.getenv('TARGET_SYSTEM_REPLICAS', 5)),  # Usar dados reais do Monitor
        "quality_of_media": int(os.getenv('TARGET_SYSTEM_QUALITY', 600)),
        "allocated_cpus": 6,
        "allocated_memory": 6,
        "error_rate": 0.0,
        "throughput": 0.0,
        "network_latency": 0.0,
        "active_pods": 5,
        "pending_pods": 0,
        "failed_pods": 0,
        "timestamp": datetime.now().isoformat(),
        "experiment_id": "unknown",
        "run_id": "unknown"
    }

async def generate_analysis_via_template_and_llm(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """Gera análise inteligente usando template V10.3 e LLM-Service"""
    try:
        # 1. Obter template V10.3 do Analyzer com experiment_id correto
        experiment_id = analysis_result.get('experiment_id', 'UNKNOWN')
        analyzer_template = AnalyzerTemplate()
        analyzer_template.data_collector = get_data_collector(experiment_id)
        template_v10_3 = analyzer_template.get_analyzer_template()
        
        # 2. Preencher template com dados focados nas métricas principais
        template_context = {
            'analysis_timestamp': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'experiment_id': analysis_result.get('experiment_id', 'UNKNOWN'),
            
            # Métricas principais (dados reais monitorados)
            'used_system_cpu': analysis_result.get('cpu_usage_percent', 0),
            'used_system_memory': analysis_result.get('memory_usage_percent', 0),
            'median_response_time': analysis_result.get('kube_znn_response_time_ms', 0),
            
            # Descrições de range
            'cpu_range_description': analysis_result.get('cpu_range_description', 'unknown range'),
            'memory_range_description': analysis_result.get('memory_range_description', 'unknown range'),
            'response_time_range_description': analysis_result.get('response_time_range_description', 'unknown range'),
            
            # Status do sistema
            'system_status': analysis_result.get('system_status', 'operational'),
            
            # Carga de requests (sempre utilizada)
            'concurrent_users': analysis_result.get('concurrent_users', 30),
            'request_rate': analysis_result.get('request_rate', 3.0),
            'session_duration': analysis_result.get('session_duration', 120),
            'load_pattern': analysis_result.get('load_pattern', 'burst'),
            'load_pattern_description': analysis_result.get('load_pattern_description', 'Burst pattern'),
            'current_load_description': analysis_result.get('load_description', 'Moderate load'),
            
            # Configuração do target system (usar dados reais do Monitor)
            'target_system_pods': analysis_result.get('active_pods', analysis_result.get('target_system_pods', 5)),
            'quality_of_media': analysis_result.get('quality_of_media', 600),
            'target_system_architecture': 'Microservices',
            
            # Configuração da infraestrutura
            'allocated_cpus': analysis_result.get('allocated_cpus', 6),
            'allocated_memory': analysis_result.get('allocated_memory', 6),
            
            # Informações adicionais (valores reais do Monitor)
            'error_rate': analysis_result.get('error_rate', 0.0),
            'throughput': analysis_result.get('throughput', 0.0),
            'network_latency': analysis_result.get('network_latency', 0.0),
            'active_pods': analysis_result.get('active_pods', 5),
            'pending_pods': analysis_result.get('pending_pods', 0),
            'failed_pods': analysis_result.get('failed_pods', 0),
            'health_criterion': analysis_result.get('health_criterion', 'operational')
        }
        
        # 3. Coletar template com variáveis utilizadas
        analyzer_template.data_collector.collect_template(
            service_name="analyzer",
            template_name="analyzer_v10_3",
            template_content=template_v10_3,
            variables=template_context,
            metadata={
                "template_version": "v10.3",
                "experiment_id": analysis_result.get('experiment_id', 'UNKNOWN')
            }
        )
        
        # 4. Gerar prompt COMPLETO a partir do template v10.3
        analysis_prompt = template_v10_3.format(**template_context)
        
        # 5. Coletar prompt gerado
        analyzer_template.data_collector.collect_llm_interaction(
            service_name="analyzer",
            request_data={"prompt": analysis_prompt, "context": template_context},
            response_data={"analysis": analysis_result},
            metadata={"template_version": "v10.3", "experiment_id": analysis_result.get('experiment_id', 'UNKNOWN')}
        )
        
        # 6. Chamar LLM-Service com o prompt COMPLETO gerado
        llm_service_url = "http://llm-service:8000/generate-prompt"
        
        llm_request_data = {
            "context": template_context,
            "prompt": analysis_prompt,
            "prompt_type": "analysis_generation",
            "category": "analyzer_v10_3"
        }
        
        # 7. Coletar requisição para LLM-Service
        analyzer_template.data_collector.collect_llm_interaction(
            service_name="analyzer",
            request_data=llm_request_data,
            response_data={},
            metadata={
                "template_version": "v10.3",
                "experiment_id": analysis_result.get('experiment_id', 'UNKNOWN'),
                "prompt_length": len(analysis_prompt)
            }
        )
        
        # Log da requisição ao LLM Service
        analyzer_logger.log_llm_request(llm_request_data)
        
        @retry_on_failure(max_retries=3, backoff_factor=1, timeout_increment=30)
        def call_llm_service():
            return requests.post(
                llm_service_url,
                json=llm_request_data,
                timeout=120,  # Increased timeout for LLM operations
                headers={'Content-Type': 'application/json'}
            )
        
        response = call_llm_service()
        
        if response.status_code == 200:
            llm_response_data = response.json()
            generated_prompt = llm_response_data.get('prompt', analysis_prompt)
            llm_analysis = llm_response_data.get('response', '')
            
            # Log da resposta do LLM Service
            analyzer_logger.log_llm_response(llm_response_data, response.status_code)
            
            # 7. Coletar interação completa com LLM-Service
            analyzer_template.data_collector.collect_llm_interaction(
                service_name="analyzer",
                request_data=llm_request_data,
                response_data=llm_response_data,
                metadata={
                    "template_version": "v10.3",
                    "experiment_id": analysis_result.get('experiment_id', 'UNKNOWN'),
                    "prompt_type": "analysis_generation"
                }
            )
            
            logger.info(f"LLM-Service gerou análise via template V10.3")
            
            return {
                'template_v10_3_applied': True,
                'template_v10_3_context': template_context,
                'template_v10_3_prompt': generated_prompt,
                'llm_analysis': llm_analysis,
                'llm_enhanced': True,
                'analysis_method': 'template_v10_3_llm'
            }
        else:
            logger.error(f"Erro no LLM-Service: {response.status_code}")
            return {
                'template_v10_3_applied': True,
                'template_v10_3_context': template_context,
                'template_v10_3_prompt': analysis_prompt,
                'llm_analysis': 'LLM-Service não disponível',
                'llm_enhanced': False,
                'analysis_method': 'template_v10_3_only'
            }
            
    except Exception as e:
        logger.error(f"Erro ao gerar análise via template: {e}")
        return {
            'template_v10_3_applied': False,
            'template_v10_3_context': {},
            'template_v10_3_prompt': '',
            'llm_analysis': f'Erro: {str(e)}',
            'llm_enhanced': False,
            'analysis_method': 'error'
        }

async def notify_planner(analysis_data: Dict[str, Any]):
    """Notifica o Planner sobre a análise concluída"""
    try:
        planner_url = os.getenv('PLANNER_URL', 'http://planner:8000')
        
        # Garantir que o Planner receba exatamente as mesmas variáveis analisadas
        planner_data = {
            "run_id": analysis_data.get("run_id", "unknown"),
            "experiment_id": analysis_data.get("experiment_id", "unknown"),
            "correlation_id": analysis_data.get("correlation_id", "unknown"),
            "analysis": analysis_data,
            # Variáveis de carga que DEVEM ser idênticas às analisadas
            "consistent_load_variables": {
                "concurrent_users": analysis_data.get("concurrent_users"),
                "request_rate": analysis_data.get("request_rate"),
                "session_duration": analysis_data.get("session_duration"),
                "load_pattern": analysis_data.get("load_pattern"),
                "load_pattern_description": analysis_data.get("load_pattern_description"),
                "current_load_description": analysis_data.get("load_description")
            }
        }
        
        # Enviar análise para o Planner
        @retry_on_failure(max_retries=3, backoff_factor=1, timeout_increment=30)
        def call_planner():
            return requests.post(
                f"{planner_url}/plan",
                json=planner_data,
                timeout=90  # Increased timeout for planner communication
            )
        
        response = call_planner()
        
        if response.status_code == 200:
            # Coletar mensagem para o sistema de coleta de dados
            # data_collector = get_data_collector()
            # data_collector.collect_message(
            #     message_type=MessageType.ANALYZER_TO_PLANNER,
            #     source_service="analyzer",
            #     target_service="planner",
            #     message_data=analysis_data,
            #     metadata={
            #         "response_status": response.status_code,
            #         "planner_response": response.json()
            #     }
            # )
            logger.info("Planner notificado com sucesso")
        else:
            logger.error(f"Erro ao notificar Planner: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Erro ao notificar Planner: {e}")

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_system(request: AnalysisRequest):
    """Analisa o estado do sistema e gera recomendações"""
    global analyzer_logger
    
    try:
        # Inicializar logger se não existir
        if analyzer_logger is None:
            analyzer_logger = AnalyzerLogger(request.experiment_id, request.correlation_id)
        
        logger.info(f"Iniciando análise para experimento {request.experiment_id}")
        
        # Log do início da execução
        analyzer_logger.log_execution_start(request.dict())
        
        # Usar dados da requisição diretamente (vêm do Monitor)
        cpu_usage = request.cpu_usage_percent
        memory_usage = request.memory_usage_percent
        response_time = request.kube_znn_response_time_ms
        error_rate = request.error_rate
        throughput = request.throughput
        network_latency = request.network_latency
        
        logger.info(f"Dados de monitoramento: CPU={cpu_usage:.2f}%, Memory={memory_usage:.2f}%, ResponseTime={response_time}ms, ErrorRate={error_rate}%, Throughput={throughput}req/s, NetworkLatency={network_latency}ms")
        
        # Determinar critério de saúde
        health_criterion = get_health_criterion(cpu_usage, memory_usage, response_time)
        
        # Gerar descrições dos ranges
        cpu_range_description = get_range_description(
            cpu_usage,
            [25, 60],
            ["within healthy range (<25%)", "within saturated range (25-60%)", "within critical range (>60%)"]
        )
        
        memory_range_description = get_range_description(
            memory_usage,
            [30, 70],
            ["within healthy range (<30%)", "within saturated range (30-70%)", "within critical range (>70%)"]
        )
        
        response_time_range_description = get_range_description(
            response_time,
            [14, 70],
            ["within healthy range (<14ms)", "within saturated range (14-70ms)", "within critical range (>70ms)"]
        )
        
        # Passar dados brutos para o LLM fazer a análise inteligente
        # Não fazer hardcoded logic - deixar o LLM decidir
        
        # Preparar dados para análise
        analysis_data = {
            'experiment_id': request.experiment_id,
            'cpu_usage_percent': cpu_usage,
            'memory_usage_percent': memory_usage,
            'kube_znn_response_time_ms': response_time,
            'error_rate': error_rate,
            'throughput': throughput,
            'network_latency': network_latency,
            'cpu_range_description': cpu_range_description,
            'memory_range_description': memory_range_description,
            'response_time_range_description': response_time_range_description,
            'system_status': 'operational',
            'quality_of_media': request.quality_of_media,
            'concurrent_users': request.concurrent_users,
            'request_rate': request.request_rate,
            'session_duration': request.session_duration,
            'load_pattern': request.load_pattern,
            'load_pattern_description': request.load_pattern_description,
            'load_description': request.load_description,
            'health_criterion': health_criterion,
            'target_system_pods': request.target_system_pods,
            'active_pods': request.active_pods,
            'pending_pods': request.pending_pods,
            'failed_pods': request.failed_pods,
            'allocated_cpus': request.allocated_cpus,
            'allocated_memory': request.allocated_memory
        }
        
        # Gerar análise via template e LLM
        llm_result = await generate_analysis_via_template_and_llm(analysis_data)
        
        # Parse LLM response to get test recommendation
        try:
            # Limpar caracteres de escape inválidos antes do parsing
            llm_analysis_text = llm_result['llm_analysis']
            
            # Remover caracteres de escape inválidos comuns
            llm_analysis_text = llm_analysis_text.replace('\\"', '"')
            llm_analysis_text = llm_analysis_text.replace('\\n', '\n')
            llm_analysis_text = llm_analysis_text.replace('\\t', '\t')
            llm_analysis_text = llm_analysis_text.replace('\\r', '\r')
            llm_analysis_text = llm_analysis_text.replace('\\_', '_')
            llm_analysis_text = llm_analysis_text.replace('\\|', '|')
            
            # Tentar encontrar o JSON válido dentro da resposta
            import re
            json_match = re.search(r'\{.*\}', llm_analysis_text, re.DOTALL)
            if json_match:
                llm_analysis_text = json_match.group()
            
            llm_analysis = json.loads(llm_analysis_text)
            test_recommendation = {
                "test_type": llm_analysis['analysis_summary']['recommended_test_type'],
                "justification": llm_analysis['analysis_summary']['justification'],
                "priority": llm_analysis['analysis_summary']['priority']
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"LLM JSON parsing failed: {e} - LLM Mistral deve sempre retornar JSON válido")
            logger.error(f"LLM response content: {llm_result['llm_analysis'][:500]}...")
            
            # Fallback: usar análise baseada em métricas
            failed_pods = request.failed_pods
            pending_pods = request.pending_pods
            test_recommendation = determine_test_type_from_metrics(cpu_usage, memory_usage, response_time, error_rate, failed_pods, pending_pods)
            logger.warning(f"Usando fallback de análise: {test_recommendation}")
        
        # COMENTADO: Fallback removido - sempre usar LLM Mistral
        # test_recommendation = determine_test_type_from_metrics(cpu_usage, memory_usage, response_time)
        
        # Criar resposta da análise
        analysis_response = AnalysisResponse(
            experiment_id=request.experiment_id,
            health_criterion=health_criterion,
            cpu_range_description=cpu_range_description,
            memory_range_description=memory_range_description,
            response_time_range_description=response_time_range_description,
            analysis_timestamp=datetime.now().isoformat(),
            template_v10_3_applied=llm_result['template_v10_3_applied'],
            template_v10_3_prompt=llm_result['template_v10_3_prompt'],
            llm_analysis=llm_result['llm_analysis'],
            llm_enhanced=llm_result['llm_enhanced'],
            recommended_test_type=test_recommendation['test_type'],
            test_justification=test_recommendation['justification'],
            test_priority=test_recommendation['priority'],
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage,
            kube_znn_response_time_ms=response_time
        )
        
        # Adicionar dados completos para coleta
        analysis_response_dict = analysis_response.dict()
        analysis_response_dict['monitoring_data'] = analysis_data
        analysis_response_dict['llm_request'] = llm_result.get('llm_request', {})
        analysis_response_dict['llm_response'] = llm_result.get('llm_response', {})
        
        # Salvar análise no Knowledge Service
        try:
            knowledge_data = {
                "analysis_result": analysis_response.dict(),
                "source": "analyzer_service",
                "timestamp": datetime.now().isoformat(),
                "experiment_id": request.experiment_id
            }
            
            # Armazenar no Redis
            redis_key = f"analysis_{request.experiment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            redis_client.setex(redis_key, 3600, json.dumps(knowledge_data))
            
            # Coletar mensagem para o Knowledge
            # data_collector = get_data_collector()
            # data_collector.collect_message(
            #     message_type=MessageType.ANALYZER_TO_KNOWLEDGE,
            #     source_service="analyzer",
            #     target_service="knowledge",
            #     message_data=knowledge_data,
            #     metadata={
            #         "analysis_method": llm_result.get('analysis_method', 'unknown'),
            #         "health_criterion": health_criterion
            #     }
            # )
            
        except Exception as e:
            logger.error(f"Erro ao salvar análise no Knowledge: {e}")
        
        # Notificar o Planner
        try:
            await notify_planner(analysis_response.dict())
        except Exception as e:
            logger.error(f"Erro ao notificar Planner: {e}")
        
        return analysis_response
        
    except Exception as e:
        logger.error(f"Erro na análise: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze/auto")
async def analyze_system_auto():
    """Análise automática usando dados mais recentes do monitoramento"""
    try:
        logger.info("Iniciando análise automática")
        
        # Obter dados mais recentes do monitoramento
        monitoring_data = await get_latest_monitoring_data()
        
        # Criar request automático com dados do monitoramento
        auto_request = AnalysisRequest(
            experiment_id=os.getenv('EXPERIMENT_ID', 'UNKNOWN'),
            cpu_usage_percent=monitoring_data.get("cpu_usage_percent", 0.0),
            memory_usage_percent=monitoring_data.get("memory_usage_percent", 0.0),
            kube_znn_response_time_ms=monitoring_data.get("kube_znn_response_time_ms", 0.0),
            error_rate=monitoring_data.get("error_rate", 0.0),
            throughput=monitoring_data.get("throughput", 0.0),
            network_latency=monitoring_data.get("network_latency", 0.0),
            quality_of_media=int(os.getenv('QUALITY_OF_MEDIA', '600')),
            concurrent_users=int(os.getenv('CONCURRENT_USERS', '30')),
            request_rate=float(os.getenv('REQUEST_RATE', '3.0')),
            session_duration=int(os.getenv('SESSION_DURATION', '120')),
            load_pattern=os.getenv('LOAD_PATTERN', 'burst'),
            load_pattern_description=os.getenv('LOAD_PATTERN_DESCRIPTION', 'Burst pattern'),
            load_description=os.getenv('LOAD_DESCRIPTION', 'Moderate load'),
            # CORREÇÃO: Usar dados reais de pods do Monitor
            active_pods=monitoring_data.get("active_pods", 3),
            pending_pods=monitoring_data.get("pending_pods", 0),
            failed_pods=monitoring_data.get("failed_pods", 0),
            allocated_cpus=int(os.getenv('ALLOCATED_CPUS', '6')),
            allocated_memory=int(os.getenv('ALLOCATED_MEMORY', '6'))
        )
        
        # Executar análise
        result = await analyze_system(auto_request)
        
        # Salvar resultado no Redis
        redis_key = f"analysis_{auto_request.experiment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        redis_client.setex(redis_key, 3600, json.dumps(result.dict()))
        
        logger.info(f"Análise automática concluída para experimento {auto_request.experiment_id}")
        return result
        
    except Exception as e:
        logger.error(f"Erro na análise automática: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "analyzer", 
        "version": "v16.7.8",
        "timestamp": datetime.now().isoformat(),
        "analyzer_interval": ANALYZER_INTERVAL
    }

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint"""
    try:
        # Verificar conectividade com Redis
        redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
        redis_client.ping()
        
        # Verificar conectividade com LLM Service
        llm_response = requests.get("http://llm-service:8000/health", timeout=5)
        
        return {
            "status": "ready", 
            "service": "analyzer",
            "dependencies": {
                "redis": "connected",
                "llm-service": "connected" if llm_response.status_code == 200 else "disconnected"
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "not_ready",
            "service": "analyzer", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Analyzer Service",
        "version": "v16.7.8",
        "description": "Microserviço para análise do estado do sistema",
        "endpoints": {
            "/analyze": "Analisa o estado do sistema",
            "/analyze/auto": "Análise automática usando dados do monitoramento",
            "/health": "Health check"
        },
        "configuration": {
            "analyzer_interval": ANALYZER_INTERVAL,
            "knowledge_url": KNOWLEDGE_URL
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
