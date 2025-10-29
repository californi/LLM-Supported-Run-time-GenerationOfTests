# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import json
import requests
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import os
import logging
from enum import Enum
from dataclasses import dataclass, asdict

# Template V10.3 Planner integrado
class PlannerTemplate:
    def __init__(self):
        self.template_version = "v10.3"
        self.target_system = "Kube-znn"
        
    def get_planner_template(self) -> str:
        return """Generate test plan for kube-znn service based on system metrics.

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

ANALYSIS:
- Status: {system_status}
- Test Type: {recommended_test_type}
- Priority: {test_priority}
- Justification: {test_justification}

REQUIREMENT: Generate tests ONLY for "{recommended_test_type}" type.

TEST GUIDELINES:
- response_time: latency, performance, resource efficiency, network tests, pod metrics, service endpoints, resource monitoring, CPU/memory usage, response time validation, endpoint accessibility
- reachability: connectivity, availability, pod status, health checks, service discovery, network policies, pod readiness, service endpoints, DNS resolution, port accessibility
- load: capacity, scalability, stress, resource limits, throughput, horizontal pod autoscaling, resource utilization, performance degradation, bottleneck identification

Generate comprehensive test suites based on system state. Create appropriate kubectl commands dynamically based on the recommended test type. Commands should validate specific aspects: pod metrics for response_time, connectivity for reachability, and resource limits for load tests. Include id, description, command, expected_output, test_type, success_criteria, failure_indicators, and oracle_validation for each command.

JSON FORMAT:
{{
  "test_cases": [
    {{
      "id": "test_1",
      "name": "{recommended_test_type} - Basic Validation", 
      "description": "Comprehensive {recommended_test_type} test covering fundamental system aspects",
      "test_type": "{recommended_test_type}",
      "priority": "{test_priority}",
      "expected_result": "System demonstrates optimal {recommended_test_type} characteristics",
      "success_criteria": "All {recommended_test_type} metrics within acceptable thresholds",
      "failure_indicators": "Any {recommended_test_type} metric exceeds critical thresholds"
    }},
    {{
      "id": "test_2",
      "name": "{recommended_test_type} - Resource Impact Analysis", 
      "description": "Evaluate {recommended_test_type} behavior under current resource constraints",
      "test_type": "{recommended_test_type}",
      "priority": "{test_priority}",
      "expected_result": "System maintains {recommended_test_type} performance despite resource limitations",
      "success_criteria": "Resource usage remains stable while {recommended_test_type} metrics are optimal",
      "failure_indicators": "Resource constraints negatively impact {recommended_test_type} performance"
    }},
    {{
      "id": "test_3",
      "name": "{recommended_test_type} - Load Pattern Validation", 
      "description": "Validate {recommended_test_type} characteristics under current load pattern",
      "test_type": "{recommended_test_type}",
      "priority": "{test_priority}",
      "expected_result": "System handles current load pattern with optimal {recommended_test_type}",
      "success_criteria": "{recommended_test_type} remains consistent throughout load pattern",
      "failure_indicators": "Load pattern causes {recommended_test_type} degradation"
    }},
    {{
      "id": "test_4",
      "name": "{recommended_test_type} - Infrastructure Validation", 
      "description": "Comprehensive {recommended_test_type} validation across all infrastructure components",
      "test_type": "{recommended_test_type}",
      "priority": "{test_priority}",
      "expected_result": "All infrastructure components demonstrate optimal {recommended_test_type}",
      "success_criteria": "Pods, services, and network components show consistent {recommended_test_type}",
      "failure_indicators": "Infrastructure components show inconsistent {recommended_test_type} behavior"
    }}
  ],
  "kubectl_commands": []
}}

Return only valid JSON."""

# Data Collector integrado
class MessageType(Enum):
    """Message types in the MAPEK system"""
    PLANNER_TO_KNOWLEDGE = "planner_to_knowledge"
    PLANNER_TO_LLM = "planner_to_llm"
    LLM_TO_PLANNER = "llm_to_planner"
    PLANNER_TO_EXECUTOR = "planner_to_executor"

class DataType(Enum):
    """Types of collected data"""
    TEMPLATE = "template"
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
        self.knowledge_url = os.getenv('KNOWLEDGE_URL', 'http://knowledge:8000')
        try:
            self.redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
            # Test connection
            self.redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
        
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
                "filled_template": template_content  # Don't format to avoid errors
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
            entry_id = f"{entry.data_type}_{entry.experiment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            entry_dict = asdict(entry)
            entry_dict['entry_id'] = entry_id
            
            redis_key = f"data_collection:{entry_id}"
            self.redis_client.setex(redis_key, 86400, json.dumps(entry_dict))
            
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
    """Gets data collector instance with lazy initialization"""
    global data_collector
    if data_collector is None:
        data_collector = DataCollector(experiment_id)
    return data_collector

class PlannerLogger:
    """Detailed logging system for the Planner"""
    
    def __init__(self, experiment_id: str, run_id: str, correlation_id: str = None):
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.correlation_id = correlation_id or f"corr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_dir = f"/app/logs/planner"
        os.makedirs(self.log_dir, exist_ok=True)
        
    def log_execution_start(self, request_data: Dict[str, Any]):
        """Log of the start of Planner execution"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "service": "planner",
            "action": "execution_start",
            "request_data": request_data,
            "analysis_received": {
                "recommended_test_type": request_data.get("analysis", {}).get("recommended_test_type"),
                "test_justification": request_data.get("analysis", {}).get("test_justification"),
                "test_priority": request_data.get("analysis", {}).get("test_priority"),
                "cpu_usage_percent": request_data.get("analysis", {}).get("cpu_usage_percent"),
                "memory_usage_percent": request_data.get("analysis", {}).get("memory_usage_percent"),
                "kube_znn_response_time_ms": request_data.get("analysis", {}).get("kube_znn_response_time_ms")
            }
        }
        
        log_file = f"{self.log_dir}/planner_execution_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner execution log saved: {log_file}")
        
    def log_knowledge_data_read(self, knowledge_data: Dict[str, Any]):
        """Log dos dados lidos do Knowledge Service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "knowledge_data_read",
            "source_service": "knowledge",
            "knowledge_data": knowledge_data,
            "data_summary": {
                "analysis_keys": list(knowledge_data.get("analysis", {}).keys()) if knowledge_data.get("analysis") else [],
                "monitoring_keys": list(knowledge_data.get("monitoring_data", {}).keys()) if knowledge_data.get("monitoring_data") else []
            }
        }
        
        log_file = f"{self.log_dir}/planner_knowledge_read_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner knowledge data read log saved: {log_file}")
        
    def log_template_generation(self, template_content: str, template_context: Dict[str, Any], filled_prompt: str):
        """Log of template and prompt generation"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "template_generation",
            "template_content": template_content,
            "template_context": template_context,
            "filled_prompt": filled_prompt,
            "template_version": "v10.3",
            "prompt_length": len(filled_prompt),
            "context_summary": {
                "recommended_test_type": template_context.get("recommended_test_type"),
                "cpu_usage": template_context.get("used_system_cpu"),
                "memory_usage": template_context.get("used_system_memory"),
                "response_time": template_context.get("median_response_time")
            }
        }
        
        log_file = f"{self.log_dir}/planner_template_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner template generation log saved: {log_file}")
        
    def log_llm_request(self, llm_request_data: Dict[str, Any]):
        """Log of the request sent to the LLM-service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "llm_request",
            "target_service": "llm-service",
            "llm_request_data": llm_request_data,
            "request_summary": {
                "prompt_type": llm_request_data.get("prompt_type"),
                "category": llm_request_data.get("category"),
                "prompt_length": len(llm_request_data.get("prompt", "")),
                "context_keys": list(llm_request_data.get("context", {}).keys()),
                "recommended_test_type": llm_request_data.get("context", {}).get("recommended_test_type")
            }
        }
        
        log_file = f"{self.log_dir}/planner_llm_request_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner LLM request log saved: {log_file}")
        
    def log_llm_response(self, llm_response_data: Dict[str, Any], llm_analysis: str):
        """Log da resposta recebida do LLM-service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "llm_response",
            "source_service": "llm-service",
            "llm_response_data": llm_response_data,
            "llm_analysis": llm_analysis,
            "response_summary": {
                "response_length": len(str(llm_analysis)) if llm_analysis else 0,
                "is_json": self._is_valid_json(str(llm_analysis)) if llm_analysis else False,
                "contains_test_cases": "test_cases" in str(llm_analysis) if llm_analysis else False,
                "contains_kubectl_commands": "kubectl_commands" in str(llm_analysis) if llm_analysis else False,
                "test_cases_count": self._count_test_cases(llm_analysis),
                "commands_count": self._count_commands(llm_analysis)
            }
        }
        
        log_file = f"{self.log_dir}/planner_llm_response_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner LLM response log saved: {log_file}")
        
    def log_executor_notification(self, executor_url: str, notification_data: Dict[str, Any], response_status: int = None, response_data: Any = None):
        """Log of the notification sent to the Executor"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "executor_notification",
            "target_service": "executor",
            "executor_url": executor_url,
            "notification_data": notification_data,
            "response_status": response_status,
            "response_data": response_data,
            "success": response_status == 200 if response_status else None,
            "notification_summary": {
                "test_cases_count": len(notification_data.get("test_cases", [])),
                "kubectl_commands_count": len(notification_data.get("kubectl_commands", [])),
                "experiment_id": notification_data.get("experiment_id"),
                "run_id": notification_data.get("run_id")
            }
        }
        
        log_file = f"{self.log_dir}/planner_executor_notification_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner executor notification log saved: {log_file}")
        
    def log_knowledge_storage(self, knowledge_data: Dict[str, Any], storage_success: bool):
        """Log do armazenamento de dados no Knowledge"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "knowledge_storage",
            "target_service": "knowledge",
            "knowledge_data": knowledge_data,
            "storage_success": storage_success,
            "storage_summary": {
                "test_cases_count": len(knowledge_data.get("test_cases", [])),
                "kubectl_commands_count": len(knowledge_data.get("kubectl_commands", [])),
                "service": knowledge_data.get("service"),
                "timestamp": knowledge_data.get("timestamp")
            }
        }
        
        log_file = f"{self.log_dir}/planner_knowledge_storage_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner knowledge storage log saved: {log_file}")
        
    def log_execution_complete(self, final_result: Dict[str, Any]):
        """Log of the completion of Planner execution"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "planner",
            "action": "execution_complete",
            "final_result": final_result,
            "execution_summary": {
                "test_cases_count": len(final_result.get("test_cases", [])),
                "kubectl_commands_count": len(final_result.get("kubectl_commands", [])),
                "template_applied": final_result.get("template_applied"),
                "llm_enhanced": final_result.get("llm_enhanced"),
                "executor_result_success": final_result.get("executor_result", {}).get("success") if final_result.get("executor_result") else None
            }
        }
        
        log_file = f"{self.log_dir}/planner_complete_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Planner execution complete log saved: {log_file}")
        
    def _is_valid_json(self, text: str) -> bool:
        """Verifies if the text is valid JSON"""
        try:
            json.loads(text)
            return True
        except:
            return False
            
    def _count_test_cases(self, text: str) -> int:
        """Counts the number of test cases in the text"""
        try:
            data = json.loads(text)
            return len(data.get("test_cases", []))
        except:
            return 0
            
    def _count_commands(self, text: str) -> int:
        """Counts the number of kubectl commands in the text"""
        try:
            data = json.loads(text)
            return len(data.get("kubectl_commands", []))
        except:
            return 0

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instanciar logger global
planner_logger = None

app = FastAPI(title="Planner Service", version="v10.4")

# Service URLs
KNOWLEDGE_URL = os.getenv('KNOWLEDGE_URL', 'http://knowledge:8000')
LLM_SERVICE_URL = os.getenv('LLM_SERVICE_URL', 'http://llm-service:8000')

# Redis client
redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

def correct_kubectl_commands(kubectl_commands: List[Dict]) -> List[Dict]:
    """Corrects incorrect kubectl commands generated by the LLM"""
    logger.info("Starting kubectl command correction...")
    
    corrected_commands = []
    
    for cmd in kubectl_commands:
        original_command = cmd.get('command', '')
        logger.info(f"Comando original: {original_command}")
        
        # Apply corrections
        corrected_command = original_command
        
        # Correção 1: kube-znn-simple-service -> kube-znn
        corrected_command = corrected_command.replace('kube-znn-simple-service', 'kube-znn')
        
        # Correção 2: porta 80 -> 80 (manter porta 80 para kube-znn)
        # if ':80/' in corrected_command and ':8080/' not in corrected_command:
        #     corrected_command = corrected_command.replace(':80/', ':8080/')
        
        # Correção 3: app=kube-znn -> usar label selector genérico para kube-znn*
        corrected_command = corrected_command.replace('-l app=kube-znn', "-l 'app in (kube-znn*)'")
        corrected_command = corrected_command.replace('app=kube-znn-', 'app in (kube-znn*)')
        
        # Correção 4: endpoint / -> /health (mais robusta)
        if 'kube-znn.default.svc.cluster.local:8080' in corrected_command and '/health' not in corrected_command:
            corrected_command = corrected_command.replace('kube-znn.default.svc.cluster.local:8080', 'kube-znn.default.svc.cluster.local:8080/health')
        
        # Correção 5: Pods hardcoded -> Service discovery
        # Substituir nomes hardcoded por service discovery
        pod_replacements = [
            ('monitor-8b58c5b4f-pd6vd', "$(kubectl get pods -n mapek-v15 -l app=monitor -o jsonpath='{.items[0].metadata.name}')"),
            ('analyzer-7bf5498894-tnmvh', "$(kubectl get pods -n mapek-v15 -l app=analyzer -o jsonpath='{.items[0].metadata.name}')"),
            ('planner-868cd6db79-xbr4k', "$(kubectl get pods -n mapek-v15 -l app=planner -o jsonpath='{.items[0].metadata.name}')"),
            ('executor-d5f6d547d-598dt', "$(kubectl get pods -n mapek-v15 -l app=executor -o jsonpath='{.items[0].metadata.name}')"),
            ('monitor-7768ffc9c-49wwj', "$(kubectl get pods -n mapek-v15 -l app=monitor -o jsonpath='{.items[0].metadata.name}')"),
            ('analyzer-7cccc64c8-qt7nd', "$(kubectl get pods -n mapek-v15 -l app=analyzer -o jsonpath='{.items[0].metadata.name}')"),
            ('planner-dbff85988-zp6hv', "$(kubectl get pods -n mapek-v15 -l app=planner -o jsonpath='{.items[0].metadata.name}')")
        ]
        
        for old_pod, new_pod_discovery in pod_replacements:
            corrected_command = corrected_command.replace(old_pod, new_pod_discovery)
        
        # Correção 6: Corrigir expected_output_pattern se necessário
        if 'expected_output_pattern' in cmd:
            pattern = cmd['expected_output_pattern']
            if 'kube-znn-simple-service' in pattern:
                cmd['expected_output_pattern'] = pattern.replace('kube-znn-simple-service', 'kube-znn')
        
        logger.info(f"Comando corrigido: {corrected_command}")
        
        # Atualizar comando no dict
        cmd['command'] = corrected_command
        corrected_commands.append(cmd)
    
    logger.info(f"Correction completed: {len(corrected_commands)} commands processed")
    return corrected_commands

# Instantiate templates
planner_template = PlannerTemplate()
data_collector = None

class TestPlanRequest(BaseModel):
    run_id: str
    experiment_id: str
    correlation_id: str = "unknown"
    analysis: Dict[str, Any]

class TestPlanResponse(BaseModel):
    timestamp: str
    test_cases: List[Dict[str, Any]]
    kubectl_commands: List[Dict[str, Any]]
    analysis: Dict[str, Any]
    priority_criteria: Dict[str, Any]
    template_applied: bool
    llm_enhanced: bool
    llm_response: str = ""

async def save_planner_data_to_knowledge(experiment_id: str, run_id: str, prompt: str, test_plan: Dict, kubectl_commands: List[Dict], test_cases: List[Dict]) -> Dict[str, Any]:
    """Salva dados do Planner no Knowledge Service"""
    try:
        logger.info(f"Salvando dados do Planner no Knowledge - experimento {experiment_id}")
        
        knowledge_url = f"{KNOWLEDGE_URL}/data-collection"
        planner_data = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "data_type": "planner_data",
            "source_service": "planner",
            "target_service": "executor",
            "data": {
                "prompt": prompt,
                "test_plan": test_plan,
                "kubectl_commands": kubectl_commands,
                "test_cases": test_cases
            },
            "metadata": {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "total_commands": len(kubectl_commands),
                "total_test_cases": len(test_cases)
            }
        }
        
        logger.info(f"Enviando dados do Planner para Knowledge: {len(kubectl_commands)} comandos, {len(test_cases)} casos de teste")
        
        knowledge_response = requests.post(
            knowledge_url,
            json=planner_data,
            timeout=10
        )
        
        if knowledge_response.status_code == 200:
            knowledge_data = knowledge_response.json()
            logger.info(f"Planner data saved to Knowledge successfully")
            
            # Coletar dados da interação
            # data_collector = get_data_collector(experiment_id)
            # data_collector.collect_knowledge_interaction(
            #     service_name="planner",
            #     interaction_data=planner_data,
            #     metadata={
            #         "experiment_id": experiment_id,
            #         "run_id": run_id,
            #         "total_commands": len(kubectl_commands),
            #         "total_test_cases": len(test_cases)
            #     }
            # )
            
            return knowledge_data
        else:
            logger.error(f"Erro ao salvar no Knowledge: {knowledge_response.status_code}")
            return {
                "error": f"Knowledge error: {knowledge_response.status_code}",
                "success": False
            }
            
    except Exception as e:
        logger.error(f"Erro ao salvar dados do Planner no Knowledge: {e}")
        return {
            "error": str(e),
            "success": False
        }

async def call_executor_simple(experiment_id: str, run_id: str, kubectl_commands: List[Dict], test_cases: List[Dict]) -> Dict[str, Any]:
    """Envia mensagem simples para Executor"""
    try:
        logger.info(f"Enviando mensagem para Executor - experimento {experiment_id}")
        
        executor_url = "http://executor:8000/execute"
        executor_request = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "kubectl_commands": kubectl_commands,
            "test_cases": test_cases
        }
        
        logger.info(f"Enviando {len(kubectl_commands)} comandos para Executor")
        
        executor_response = requests.post(
            executor_url,
            json=executor_request,
            timeout=30
        )
        
        if executor_response.status_code == 200:
            executor_data = executor_response.json()
            logger.info(f"Executor executou comandos com sucesso")
            return executor_data
        else:
            logger.error(f"Error communicating with Executor: {executor_response.status_code}")
            return {
                "error": f"Executor error: {executor_response.status_code}",
                "success": False
            }
            
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para Executor: {e}")
        return {
            "error": str(e),
            "success": False
        }

async def call_executor(experiment_id: str, run_id: str, kubectl_commands: List[Dict], test_cases: List[Dict]) -> Dict[str, Any]:
    """Chama o Executor para executar comandos kubectl"""
    try:
        logger.info(f"Chamando Executor para experimento {experiment_id}")
        
        executor_url = "http://executor:8000/execute"
        executor_request = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "kubectl_commands": kubectl_commands,
            "test_cases": test_cases
        }
        
        logger.info(f"Enviando {len(kubectl_commands)} comandos para Executor")
        logger.info(f"Executor request: {executor_request}")
        
        executor_response = requests.post(
            executor_url,
            json=executor_request,
            timeout=90  # Increased timeout for executor communication
        )
        
        logger.info(f"Executor response status: {executor_response.status_code}")
        
        if executor_response.status_code == 200:
            executor_data = executor_response.json()
            logger.info(f"Executor executou {len(kubectl_commands)} comandos com sucesso")
            logger.info(f"Executor data: {executor_data}")
            
            # Coletar dados da execução
            try:
                data_collector = get_data_collector(experiment_id)
                data_collector.collect_execution_result(
                    service_name="planner",
                    execution_data=executor_data,
                    metadata={
                        "experiment_id": experiment_id,
                        "run_id": run_id,
                        "total_commands": len(kubectl_commands),
                        "executor_success": executor_data.get('success', False)
                    }
                )
            except Exception as e:
                logger.warning(f"Error collecting execution data: {e}")
            
            return executor_data
        else:
            logger.error(f"Error communicating with Executor: {executor_response.status_code}")
            logger.error(f"Executor response: {executor_response.text}")
            return {
                "error": f"Executor error: {executor_response.status_code}",
                "success": False,
                "response_text": executor_response.text
            }
            
    except Exception as e:
        logger.error(f"Erro ao chamar Executor: {e}")
        return {
            "error": str(e),
            "success": False
        }

async def get_monitor_data_from_knowledge() -> Dict[str, Any]:
    """Obtém dados do monitor do Knowledge Service"""
    try:
        knowledge_response = requests.get(f"{KNOWLEDGE_URL}/monitor-data", timeout=5)
        if knowledge_response.status_code == 200:
            data = knowledge_response.json()
            return data.get("data", {})
        else:
            logger.warning(f"Falha ao buscar dados do monitor: {knowledge_response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"Erro ao obter dados do monitor: {e}")
        return {}

async def store_new_test_types_in_knowledge(test_cases: List[Dict], kubectl_commands: List[Dict], experiment_id: str):
    """Detecta e armazena novos tipos de teste no Knowledge Service"""
    try:
        # Coletar todos os tipos de teste únicos
        test_types = set()
        
        for test_case in test_cases:
            test_type = test_case.get('test_type')
            if test_type:
                test_types.add(test_type)
        
        for command in kubectl_commands:
            test_type = command.get('test_type')
            if test_type:
                test_types.add(test_type)
        
        # Tipos conhecidos
        known_types = {'response_time', 'reachability', 'load'}
        
        # Identificar novos tipos
        new_types = test_types - known_types
        
        if new_types:
            logger.info(f"Novos tipos de teste detectados: {new_types}")
            
            # Preparar dados para armazenar no Knowledge
            new_test_types_data = {
                "experiment_id": experiment_id,
                "timestamp": datetime.now().isoformat(),
                "new_test_types": list(new_types),
                "test_cases_with_new_types": [
                    tc for tc in test_cases 
                    if tc.get('test_type') in new_types
                ],
                "commands_with_new_types": [
                    cmd for cmd in kubectl_commands 
                    if cmd.get('test_type') in new_types
                ],
                "metadata": {
                    "source": "planner",
                    "detection_method": "automatic",
                    "total_test_types": len(test_types),
                    "known_types": list(known_types),
                    "new_types_count": len(new_types)
                }
            }
            
            # Enviar para Knowledge Service
            knowledge_response = requests.post(
                f"{KNOWLEDGE_URL}/store-new-test-types",
                json=new_test_types_data,
                timeout=10
            )
            
            if knowledge_response.status_code == 200:
                logger.info(f"Novos tipos de teste armazenados no Knowledge: {new_types}")
            else:
                logger.warning(f"Falha ao armazenar novos tipos no Knowledge: {knowledge_response.status_code}")
        else:
            logger.info("Nenhum novo tipo de teste detectado")
            
    except Exception as e:
        logger.error(f"Erro ao armazenar novos tipos de teste: {e}")

async def generate_plan_via_template_and_llm(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate test plan using template V10.3 and LLM-Service"""
    try:
        logger.info(f"Starting plan generation via template V10.3 for experiment {analysis_data.get('experiment_id', 'UNKNOWN')}")
        logger.info(f"LLM_SERVICE_URL: {LLM_SERVICE_URL}")
        
        # 1. Get template V10.3 from Planner
        logger.info("Obtendo template V10.3 do Planner...")
        template_v10_3 = planner_template.get_planner_template()
        logger.info(f"Template obtido: {template_v10_3[:100]}...")
        
        # 3. Fill template with data focused on main metrics
        logger.info("Construindo template context...")
        
        # Usar variáveis consistentes do Analyser se disponíveis
        consistent_vars = analysis_data.get('consistent_load_variables', {})
        
        template_context = {
            # Basic context
            'experiment_id': analysis_data.get('experiment_id', 'UNKNOWN'),
            
            # Main metrics (from analysis data)
            'used_system_cpu': analysis_data.get('cpu_usage_percent', 0),
            'used_system_memory': analysis_data.get('memory_usage_percent', 0),
            'median_response_time': analysis_data.get('kube_znn_response_time_ms', 0),
            
            # Request load (USAR VARIÁVEIS CONSISTENTES DO ANALYSER)
            'concurrent_users': consistent_vars.get('concurrent_users', analysis_data.get('concurrent_users', 30)),
            'request_rate': consistent_vars.get('request_rate', analysis_data.get('request_rate', 3.0)),
            'session_duration': consistent_vars.get('session_duration', analysis_data.get('session_duration', 120)),
            'load_pattern': consistent_vars.get('load_pattern', analysis_data.get('load_pattern', 'burst')),
            'load_pattern_description': consistent_vars.get('load_pattern_description', analysis_data.get('load_pattern_description', 'Burst pattern')),
            'current_load_description': consistent_vars.get('current_load_description', analysis_data.get('load_description', 'Moderate load')),
            
            # Target system configuration (usar dados reais do Monitor)
            'target_system_pods': analysis_data.get('active_pods', analysis_data.get('target_system_pods', 5)),
            'quality_of_media': analysis_data.get('quality_of_media', int(os.getenv('TARGET_SYSTEM_QUALITY', 600))),
            'target_system_architecture': 'Microservices',
            
            # Infrastructure configuration
            'allocated_cpus': analysis_data.get('allocated_cpus', 6),
            'allocated_memory': analysis_data.get('allocated_memory', 6),
            
            # Additional information
            'error_rate': analysis_data.get('error_rate', 0.0),
            'throughput': analysis_data.get('throughput', 0.0),
            'network_latency': analysis_data.get('network_latency', 0.0),
            'active_pods': analysis_data.get('active_pods', int(os.getenv('TARGET_SYSTEM_REPLICAS', 3))),
            'pending_pods': analysis_data.get('pending_pods', 0),
            'failed_pods': analysis_data.get('failed_pods', 0),
            
            # Analysis context
            'system_status': analysis_data.get('system_status', 'operational'),
            'cpu_range_description': analysis_data.get('cpu_range_description', 'normal range'),
            'memory_range_description': analysis_data.get('memory_range_description', 'normal range'),
            'response_time_range_description': analysis_data.get('response_time_range_description', 'acceptable range'),
            'recommended_test_type': analysis_data.get('recommended_test_type', 'reachability'),
            'test_justification': analysis_data.get('test_justification', 'System analysis completed'),
            'test_priority': analysis_data.get('test_priority', 'medium')
        }
        
        # 4. Collect template with variables used
        collector = get_data_collector(analysis_data.get('experiment_id', 'UNKNOWN'))
        collector.collect_template(
            service_name="planner",
            template_name="planner_v10_3",
            template_content=template_v10_3,
            variables=template_context,
            metadata={
                "template_version": "v10.3",
                "experiment_id": analysis_data.get('experiment_id', 'E1-1-1')
            }
        )
        
        # 5. Generate complete prompt from template V10.3 (template dinâmico)
        logger.info("Gerando prompt completo a partir do template V10.3...")
        complete_prompt = template_v10_3.format(**template_context)
        logger.info(f"Prompt gerado: {complete_prompt[:200]}...")
        
        # 6. Usar LLM-Service - sem fallbacks (sempre LLM Mistral)
        logger.info("Tentando LLM-Service...")
        llm_response = None
        
        try:
            llm_request_data = {
                "context": template_context,
                "category": "planner_v10_3",
                "prompt": complete_prompt,
                "prompt_type": "test_generation"
            }
            
            # Log da requisição ao LLM Service
            planner_logger.log_llm_request(llm_request_data)
            
            llm_response = requests.post(
                f"{LLM_SERVICE_URL}/generate-prompt",
                json=llm_request_data,
                timeout=120  # Increased timeout for LLM service operations
            )
            
            if llm_response.status_code != 200:
                raise Exception(f"LLM-Service returned {llm_response.status_code}")
                
        except Exception as e:
            logger.error(f"LLM-Service falhou: {e}")
            raise HTTPException(status_code=500, detail=f"LLM-Service error: {str(e)}")
        
        if llm_response.status_code == 200:
            llm_data = llm_response.json()
            logger.info("Resposta do LLM-Service recebida com sucesso")
            
            # Log da resposta do LLM Service
            llm_response_text = llm_data.get('response', '')
            planner_logger.log_llm_response(llm_data, llm_response_text)
            
            # 7. Collect LLM interaction
            data_collector.collect_llm_interaction(
                service_name="planner",
                request_data=llm_request_data,
                response_data=llm_data,
                metadata={
                    "template_version": "v10.3",
                    "experiment_id": analysis_data.get('experiment_id', 'E1-1-1')
                }
            )
            
            # 8. Parse LLM response
            try:
                llm_response_text = llm_data.get('response', '{}')
                if isinstance(llm_response_text, str):
                    # Remove markdown code blocks if present
                    import re
                    # Remove ```json and ``` blocks
                    llm_response_text = re.sub(r'```json\s*', '', llm_response_text)
                    llm_response_text = re.sub(r'```\s*', '', llm_response_text)
                    
                    # Remove control characters that can break JSON parsing
                    llm_response_text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', llm_response_text)
                    
                    # Fix invalid escape sequences BEFORE parsing
                    # Replace invalid escapes like "\ " with " "
                    llm_response_text = re.sub(r'\\([^u"/bfnrt\\])', r'\1', llm_response_text)
                    
                    # Try to extract JSON from response
                    # Look for JSON that starts with { and ends with } (more precise)
                    json_match = re.search(r'\{.*\}', llm_response_text, re.DOTALL)
                    if json_match:
                        llm_response_text = json_match.group()
                    else:
                        # Fallback: try to find JSON between first { and last }
                        first_brace = llm_response_text.find('{')
                        last_brace = llm_response_text.rfind('}')
                        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                            llm_response_text = llm_response_text[first_brace:last_brace+1]
                    
                    # Try to fix common JSON issues
                    try:
                        plan_data = json.loads(llm_response_text)
                    except json.JSONDecodeError as json_err:
                        logger.warning(f"JSON parsing failed, attempting to fix: {json_err}")
                        
                        # CORREÇÃO 1: Remover caracteres de controle inválidos (0x00-0x1F exceto tab, newline, carriage return)
                        import re
                        # Remove control characters except tab(0x09), newline(0x0A), carriage return(0x0D)
                        fixed_json = ''.join(char for char in llm_response_text if ord(char) >= 32 or char in '\t\n\r')
                        logger.info(f"Removed {len(llm_response_text) - len(fixed_json)} invalid control characters")
                        
                        # Try to fix common issues
                        fixed_json = fixed_json.replace("'", '"')  # Replace single quotes
                        fixed_json = fixed_json.replace('\\"', '"')  # Fix escaped quotes
                        fixed_json = fixed_json.replace('\\n', '\n')  # Fix escaped newlines
                        fixed_json = fixed_json.replace('\\t', '\t')  # Fix escaped tabs
                        fixed_json = fixed_json.replace('\\r', '\r')  # Fix escaped carriage returns
                        fixed_json = fixed_json.replace('\\_', '_')   # Fix escaped underscores
                        fixed_json = fixed_json.replace('\\|', '|')   # Fix escaped pipes
                        fixed_json = re.sub(r',\s*}', '}', fixed_json)  # Remove trailing commas
                        fixed_json = re.sub(r',\s*]', ']', fixed_json)  # Remove trailing commas in arrays
                        
                        # Fix unterminated strings
                        fixed_json = re.sub(r'"([^"]*)$', r'"\1"', fixed_json)  # Close unterminated strings
                        fixed_json = re.sub(r'([^"]*)"([^"]*)$', r'\1"\2"', fixed_json)  # Fix partial strings
                        
                        # Remove invalid escape sequences that break JSON parsing
                        # Replace invalid escapes like "\ " with " "
                        fixed_json = re.sub(r'\\([^u"/bfnrt\\])', r'\1', fixed_json)
                        # Fix escaped newlines and tabs in strings
                        fixed_json = fixed_json.replace('\\n', ' ')
                        fixed_json = fixed_json.replace('\\t', ' ')
                        fixed_json = fixed_json.replace('\\r', ' ')
                        
                        # Try to complete incomplete JSON
                        if not fixed_json.strip().endswith('}'):
                            # Count braces to see if we need to close
                            open_braces = fixed_json.count('{')
                            close_braces = fixed_json.count('}')
                            if open_braces > close_braces:
                                fixed_json += '}' * (open_braces - close_braces)
                        
                        try:
                            plan_data = json.loads(fixed_json)
                        except json.JSONDecodeError as final_err:
                            # Last resort: try to extract valid JSON using ast
                            try:
                                import ast
                                # Try to parse as Python dict and convert to JSON
                                dict_data = ast.literal_eval(fixed_json)
                                plan_data = json.loads(json.dumps(dict_data))
                                logger.warning("JSON parsed using ast.literal_eval as fallback")
                            except Exception as ast_err:
                                logger.error(f"JSON parsing still failed after all fixes: {final_err}")
                                logger.error(f"AST fallback also failed: {ast_err}")
                                
                                # Final fallback: try to manually extract just the essential data
                                logger.warning("Attempting manual JSON extraction as last resort")
                                try:
                                    # Try to extract full JSON structure by finding boundaries
                                    # Look for the start of test_cases and end of kubectl_commands
                                    test_start = fixed_json.find('"test_cases"')
                                    cmds_start = fixed_json.find('"kubectl_commands"')
                                    
                                    # Try to construct valid JSON from the beginning
                                    plan_data = {"test_cases": [], "kubectl_commands": []}
                                    
                                    # Try one more time with the fixed_json but with a more lenient approach
                                    # Just skip the error and use what we can
                                    logger.warning("Attempting to salvage JSON data by ignoring parse errors")
                                    
                                    # We failed completely, but try to extract what we can
                                    logger.error(f"All JSON parsing attempts failed. Attempting partial extraction.")
                                    logger.error(f"JSON string length: {len(fixed_json)}")
                                    
                                    # Try to extract test_cases and commands from the broken JSON manually
                                    import re
                                    plan_data = {"test_cases": [], "kubectl_commands": []}
                                    
                                    # Extract test_cases using regex
                                    test_cases_matches = re.findall(r'"id":\s*"([^"]+)",\s*"name":\s*"([^"]+)",\s*"description":\s*"([^"]+)"', fixed_json)
                                    for i, (test_id, test_name, test_desc) in enumerate(test_cases_matches, 1):
                                        plan_data["test_cases"].append({
                                            "id": test_id if test_id else f"test_{i}",
                                            "name": test_name,
                                            "description": test_desc,
                                            "test_type": "load",
                                            "priority": "high"
                                        })
                                    
                                    # Extract kubectl commands using regex - improved for multiline commands
                                    cmd_matches = re.findall(r'"id":\s*"([^"]+)",\s*"description":\s*"([^"]+)",\s*"command":\s*"([^"]+)"', fixed_json, re.DOTALL)
                                    for i, (cmd_id, cmd_desc, cmd_cmd) in enumerate(cmd_matches, 1):
                                        # Clean up command (remove newlines and extra spaces)
                                        cmd_cmd = ' '.join(cmd_cmd.split())
                                        plan_data["kubectl_commands"].append({
                                            "id": cmd_id if cmd_id else f"cmd_{i}",
                                            "description": cmd_desc,
                                            "command": cmd_cmd,
                                            "test_type": "load"
                                        })
                                    
                                    # Fallback: try to extract commands with a more lenient pattern
                                    if len(plan_data["kubectl_commands"]) == 0:
                                        # Look for "kubectl " patterns and try to extract commands
                                        kubectl_matches = re.findall(r'"command":\s*"([^"]*kubectl[^"]*)"', fixed_json, re.DOTALL)
                                        for j, cmd_text in enumerate(kubectl_matches[:7], 1):
                                            cmd_text = ' '.join(cmd_text.split())
                                            plan_data["kubectl_commands"].append({
                                                "id": f"cmd_{j}",
                                                "description": "Extracted command",
                                                "command": cmd_text,
                                                "test_type": "load"
                                            })
                                    
                                    logger.info(f"Extracted {len(plan_data['test_cases'])} test_cases and {len(plan_data['kubectl_commands'])} commands from broken JSON")
                                    
                                    # This will cause the code to continue with partial plan_data
                                    # which is better than empty plan_data
                                    
                                except Exception as manual_err:
                                    logger.error(f"Manual extraction failed: {manual_err}")
                                    logger.error(f"Original response: {llm_response_text[:500]}...")
                                    logger.error(f"Fixed JSON: {fixed_json[:500]}...")
                                    # Use empty plan_data as last resort
                                    plan_data = {"test_cases": [], "kubectl_commands": []}
                else:
                    plan_data = llm_response_text
                
                logger.info("Plano de teste gerado com sucesso via LLM")
                
                # CORREÇÃO PÓS-PROCESSAMENTO: Corrigir comandos incorretos
                if 'kubectl_commands' in plan_data:
                    logger.info("Applying post-processing corrections...")
                    plan_data['kubectl_commands'] = correct_kubectl_commands(plan_data['kubectl_commands'])
                
                # SALVAR NO KNOWLEDGE: Prompt, planos, casos de testes e comandos kubectl
                logger.info("Salvando dados do Planner no Knowledge...")
                logger.info(f"Experiment ID: {analysis_data.get('experiment_id', 'UNKNOWN')}")
                logger.info(f"Run ID: {analysis_data.get('run_id', 'run_001')}")
                logger.info(f"Kubectl commands count: {len(plan_data.get('kubectl_commands', []))}")
                logger.info(f"Test cases count: {len(plan_data.get('test_cases', []))}")
                
                # Armazenar novos tipos de teste no Knowledge
                try:
                    await store_new_test_types_in_knowledge(
                        test_cases=plan_data.get('test_cases', []),
                        kubectl_commands=plan_data.get('kubectl_commands', []),
                        experiment_id=analysis_data.get('experiment_id', 'UNKNOWN')
                    )
                except Exception as e:
                    logger.error(f"Erro ao armazenar novos tipos de teste: {e}")
                
                try:
                    logger.info("Iniciando salvamento no Knowledge...")
                    knowledge_result = await save_planner_data_to_knowledge(
                        experiment_id=analysis_data.get('experiment_id', 'UNKNOWN'),
                        run_id=analysis_data.get('run_id', 'run_001'),
                        prompt=complete_prompt,
                        test_plan=plan_data,
                        kubectl_commands=plan_data.get('kubectl_commands', []),
                        test_cases=plan_data.get('test_cases', [])
                    )
                    logger.info(f"Planner data saved to Knowledge: {knowledge_result}")
                except Exception as e:
                    logger.error(f"Erro ao salvar no Knowledge: {e}")
                    knowledge_result = {"error": str(e), "success": False}
                
                # CHAMAR EXECUTOR: Executar comandos kubectl gerados pelo LLM
                logger.info("Chamando Executor para executar comandos gerados pelo LLM...")
                executor_result = await call_executor(
                    experiment_id=analysis_data.get('experiment_id', 'E1-1-1'),
                    run_id=analysis_data.get('run_id', 'run_001'),
                    kubectl_commands=plan_data.get('kubectl_commands', []),
                    test_cases=plan_data.get('test_cases', [])
                )
                
                return {
                    "timestamp": datetime.now().isoformat(),
                    "test_cases": plan_data.get('test_cases', []),
                    "kubectl_commands": plan_data.get('kubectl_commands', []),
                    "analysis": analysis_data,
                    "priority_criteria": plan_data.get('priority_criteria', {}),
                    "template_applied": True,
                    "llm_enhanced": True,
                    "llm_response": llm_data.get('response', ''),
                    "template_v10_3_prompt": complete_prompt,
                    "knowledge_result": knowledge_result,
                    "executor_result": executor_result
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Erro ao fazer parse da resposta do LLM: {e}")
                logger.error(f"Resposta recebida: {llm_data.get('response', '')}")
                raise HTTPException(status_code=500, detail=f"LLM JSON parsing error: {str(e)}")
        else:
            logger.error(f"Error communicating with LLM-Service: {llm_response.status_code}")
            raise HTTPException(status_code=500, detail=f"LLM-Service error: {llm_response.status_code}")
            
    except Exception as e:
        logger.error(f"Error in plan generation: {str(e)}")
        logger.error(f"Tipo do erro: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "planner", "timestamp": datetime.now().isoformat()}

@app.post("/plan", response_model=TestPlanResponse)
async def plan_tests(request: TestPlanRequest):
    """Generate test plan based on analysis data"""
    global planner_logger
    
    try:
        # Inicializar logger se não existir
        if planner_logger is None:
            planner_logger = PlannerLogger(request.experiment_id, request.run_id, request.correlation_id)
        
        logger.info(f"Receiving planning request for experiment {request.experiment_id}")
        
        # Log do início da execução
        planner_logger.log_execution_start(request.dict())
        
        # Generate plan using template and LLM
        plan_result = await generate_plan_via_template_and_llm(request.analysis)
        
        logger.info(f"Plano de teste gerado com sucesso para {request.experiment_id}")
        return TestPlanResponse(**plan_result)
        
    except Exception as e:
        logger.error(f"Erro no planejamento de testes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)