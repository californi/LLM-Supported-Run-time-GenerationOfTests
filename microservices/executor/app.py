#!/usr/bin/env python3
"""
Microserviço Executor - V10.3
Recebe casos de teste do Planner e executa comandos kubectl
"""

import requests
import json
import subprocess
import logging
import os
import redis
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# Data Collector integrado
from enum import Enum
from dataclasses import dataclass, asdict

class MessageType(Enum):
    """Message types in the MAPEK system"""
    EXECUTOR_TO_KNOWLEDGE = "executor_to_knowledge"
    EXECUTOR_TO_LLM = "executor_to_llm"
    LLM_TO_EXECUTOR = "llm_to_executor"
    EXECUTOR_TO_KUBERNETES = "executor_to_kubernetes"
    KUBERNETES_TO_EXECUTOR = "kubernetes_to_executor"

class DataType(Enum):
    """Types of collected data"""
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    KUBERNETES_COMMAND = "kubernetes_command"
    KUBERNETES_RESULT = "kubernetes_result"
    TEST_CASE = "test_case"
    EXECUTION_RESULT = "execution_result"

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
    
    def collect_kubernetes_command(
        self,
        service_name: str,
        command: str,
        expected_output: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Coleta comando Kubernetes gerado"""
        entry = DataCollectionEntry(
            experiment_id=self.experiment_id,
            timestamp=datetime.now().isoformat(),
            data_type=DataType.KUBERNETES_COMMAND.value,
            message_type=None,
            source_service=service_name,
            target_service="kubernetes",
            data={
                "command": command,
                "expected_output": expected_output
            },
            metadata=metadata or {}
        )
        
        return self._store_entry(entry)
    
    def collect_kubernetes_result(
        self,
        service_name: str,
        command: str,
        result: Dict[str, Any],
        success: bool,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Coleta resultado de execução de comando Kubernetes"""
        entry = DataCollectionEntry(
            experiment_id=self.experiment_id,
            timestamp=datetime.now().isoformat(),
            data_type=DataType.KUBERNETES_RESULT.value,
            message_type=None,
            source_service="kubernetes",
            target_service=service_name,
            data={
                "command": command,
                "result": result,
                "success": success
            },
            metadata=metadata or {}
        )
        
        return self._store_entry(entry)
    
    def collect_execution_result(
        self,
        service_name: str,
        execution_data: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> str:
        """Coleta resultado de execução de teste"""
        entry = DataCollectionEntry(
            experiment_id=self.experiment_id,
            timestamp=datetime.now().isoformat(),
            data_type=DataType.EXECUTION_RESULT.value,
            message_type=None,
            source_service=service_name,
            target_service=None,
            data=execution_data,
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

class ExecutorLogger:
    """Sistema de logging detalhado para o Executor"""
    
    def __init__(self, experiment_id: str, run_id: str):
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_dir = f"/app/logs/executor"
        os.makedirs(self.log_dir, exist_ok=True)
        
    def log_execution_start(self, request_data: Dict[str, Any]):
        """Log do início da execução do Executor"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "execution_start",
            "request_data": request_data,
            "execution_summary": {
                "test_cases_count": len(request_data.get("test_cases", [])),
                "kubectl_commands_count": len(request_data.get("kubectl_commands", [])),
                "experiment_id": request_data.get("experiment_id"),
                "run_id": request_data.get("run_id")
            }
        }
        
        log_file = f"{self.log_dir}/executor_execution_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor execution log saved: {log_file}")
        
    def log_knowledge_data_read(self, knowledge_data: Dict[str, Any]):
        """Log dos dados lidos do Knowledge Service"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "knowledge_data_read",
            "source_service": "knowledge",
            "knowledge_data": knowledge_data,
            "data_summary": {
                "test_cases_count": len(knowledge_data.get("test_cases", [])),
                "kubectl_commands_count": len(knowledge_data.get("kubectl_commands", [])),
                "service": knowledge_data.get("service"),
                "timestamp": knowledge_data.get("timestamp")
            }
        }
        
        log_file = f"{self.log_dir}/executor_knowledge_read_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor knowledge data read log saved: {log_file}")
        
    def log_kubectl_command_execution(self, command_data: Dict[str, Any], command_result: Dict[str, Any]):
        """Log da execução de um comando kubectl"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "kubectl_command_execution",
            "target_service": "kubernetes",
            "command_data": command_data,
            "command_result": command_result,
            "execution_summary": {
                "command_id": command_data.get("id"),
                "command": command_data.get("command"),
                "test_type": command_data.get("test_type"),
                "success": command_result.get("success"),
                "exit_code": command_result.get("exit_code"),
                "execution_time_ms": command_result.get("execution_time_ms"),
                "oracle_validation": command_result.get("oracle_validation")
            }
        }
        
        log_file = f"{self.log_dir}/executor_kubectl_{command_data.get('id', 'unknown')}_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor kubectl command execution log saved: {log_file}")
        
    def log_test_case_execution(self, test_case: Dict[str, Any], test_result: Dict[str, Any]):
        """Log da execução de um caso de teste"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "test_case_execution",
            "test_case": test_case,
            "test_result": test_result,
            "execution_summary": {
                "test_id": test_case.get("id"),
                "test_name": test_case.get("name"),
                "test_type": test_case.get("test_type"),
                "priority": test_case.get("priority"),
                "success": test_result.get("success"),
                "oracle_validation": test_result.get("oracle_validation"),
                "commands_executed": test_result.get("commands_executed", 0),
                "commands_successful": test_result.get("commands_successful", 0)
            }
        }
        
        log_file = f"{self.log_dir}/executor_test_case_{test_case.get('id', 'unknown')}_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor test case execution log saved: {log_file}")
        
    def log_oracle_validation(self, oracle_data: Dict[str, Any], validation_result: Dict[str, Any]):
        """Log da validação de oracle"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "oracle_validation",
            "oracle_data": oracle_data,
            "validation_result": validation_result,
            "validation_summary": {
                "oracle_type": oracle_data.get("type"),
                "expected_pattern": oracle_data.get("expected_pattern"),
                "actual_output": oracle_data.get("actual_output"),
                "validation_success": validation_result.get("success"),
                "validation_message": validation_result.get("message")
            }
        }
        
        log_file = f"{self.log_dir}/executor_oracle_{oracle_data.get('type', 'unknown')}_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor oracle validation log saved: {log_file}")
        
    def log_knowledge_storage(self, knowledge_data: Dict[str, Any], storage_success: bool):
        """Log do armazenamento de dados no Knowledge"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "knowledge_storage",
            "target_service": "knowledge",
            "knowledge_data": knowledge_data,
            "storage_success": storage_success,
            "storage_summary": {
                "execution_results_count": len(knowledge_data.get("execution_results", [])),
                "test_results_count": len(knowledge_data.get("test_results", [])),
                "service": knowledge_data.get("service"),
                "timestamp": knowledge_data.get("timestamp")
            }
        }
        
        log_file = f"{self.log_dir}/executor_knowledge_storage_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor knowledge storage log saved: {log_file}")
        
    def log_execution_complete(self, final_result: Dict[str, Any]):
        """Log da conclusão da execução do Executor"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "execution_complete",
            "final_result": final_result,
            "execution_summary": {
                "total_commands": final_result.get("total_commands", 0),
                "successful_commands": final_result.get("successful_commands", 0),
                "failed_commands": final_result.get("failed_commands", 0),
                "total_test_cases": final_result.get("total_test_cases", 0),
                "successful_test_cases": final_result.get("successful_test_cases", 0),
                "failed_test_cases": final_result.get("failed_test_cases", 0),
                "overall_success": final_result.get("success", False),
                "execution_time_ms": final_result.get("execution_time_ms", 0)
            }
        }
        
        log_file = f"{self.log_dir}/executor_complete_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor execution complete log saved: {log_file}")
        
    def log_test_results_summary(self, test_results: List[Dict[str, Any]]):
        """Log do resumo dos resultados de testes"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "service": "executor",
            "action": "test_results_summary",
            "test_results": test_results,
            "summary": {
                "total_tests": len(test_results),
                "successful_tests": len([r for r in test_results if r.get("success", False)]),
                "failed_tests": len([r for r in test_results if not r.get("success", False)]),
                "test_types": list(set([r.get("test_type", "unknown") for r in test_results])),
                "priority_distribution": {
                    "high": len([r for r in test_results if r.get("priority") == "high"]),
                    "medium": len([r for r in test_results if r.get("priority") == "medium"]),
                    "low": len([r for r in test_results if r.get("priority") == "low"])
                }
            }
        }
        
        log_file = f"{self.log_dir}/executor_test_results_{self.experiment_id}_{self.timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Executor test results summary log saved: {log_file}")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instanciar logger global
executor_logger = None

app = FastAPI(title="Executor Service", version="v10.3")

# Service URLs
LLM_SERVICE_URL = "http://llm-service:8000"
KNOWLEDGE_URL = "http://knowledge:8000"

# Instanciar coletor de dados (lazy initialization)
data_collector = None

class TestCaseRequest(BaseModel):
    """Request para execução de casos de teste"""
    experiment_id: str
    test_cases: List[Dict[str, Any]]
    analysis_context: Dict[str, Any]
    planning_context: Dict[str, Any]
    run_id: str = "default"

class TestCaseResponse(BaseModel):
    """Response da execução de casos de teste"""
    experiment_id: str
    executed_test_cases: List[Dict[str, Any]]
    kubectl_commands: List[Dict[str, Any]]
    execution_results: List[Dict[str, Any]]
    timestamp: str
    success: bool

class KubectlExecutionRequest(BaseModel):
    """Request para execução direta de comandos kubectl"""
    experiment_id: str
    run_id: str
    kubectl_commands: List[Dict[str, Any]]
    test_cases: List[Dict[str, Any]]
    analysis_context: Dict[str, Any] = {}
    planning_context: Dict[str, Any] = {}

class KubectlExecutionResponse(BaseModel):
    """Response da execução de comandos kubectl"""
    experiment_id: str
    run_id: str
    executed_commands: List[Dict[str, Any]]
    execution_results: List[Dict[str, Any]]
    test_case_results: List[Dict[str, Any]]
    timestamp: str
    success: bool

class KubectlCommandResponse(BaseModel):
    """Response com comandos kubectl gerados"""
    experiment_id: str
    test_case_id: str
    generated_commands: List[str]
    llm_response: str
    timestamp: str

def generate_kubectl_commands_via_llm(test_case: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Gera comandos kubectl usando LLM-Service baseado no caso de teste"""
    try:
        # Preparar contexto para o LLM-Service
        llm_context = {
            "experiment_id": context.get("experiment_id", "UNKNOWN"),
            "test_case": test_case,
            "analysis_context": context.get("analysis_context", {}),
            "planning_context": context.get("planning_context", {}),
            "target_system": context.get("target_system", "kube-znn"),
            "namespace": context.get("namespace", "default"),
            "timestamp": datetime.now().isoformat()
        }
        
        # Criar prompt para geração de comandos kubectl
        kubectl_prompt = f"""# GERAÇÃO DE COMANDOS KUBERNETES PARA CASO DE TESTE

## CONTEXTO DO EXPERIMENTO
**ID do Experimento:** {context.get('experiment_id', 'UNKNOWN')}
**Caso de Teste:** {test_case.get('id', 'TC001')}
**Nome:** {test_case.get('name', 'Teste')}
**Descrição:** {test_case.get('description', 'Descrição do teste')}

## CONFIGURAÇÃO DO SISTEMA
**Target System:** {context.get('target_system', 'kube-znn')}
**Namespace:** {context.get('namespace', 'default')}
**Estado de Saúde:** {context.get('analysis_context', {}).get('health_criterion', 'Unknown')}
**CPU Utilizada:** {context.get('analysis_context', {}).get('cpu_usage_percent', 0)}%
**Memória Utilizada:** {context.get('analysis_context', {}).get('memory_usage_percent', 0)}%
**Tempo de Resposta:** {context.get('analysis_context', {}).get('kube_znn_response_time_ms', 0)}ms

## CASO DE TESTE
**ID:** {test_case.get('id', 'TC001')}
**Nome:** {test_case.get('name', 'Teste')}
**Descrição:** {test_case.get('description', 'Descrição do teste')}
**Resultado Esperado:** {test_case.get('expected_result', 'Resultado esperado')}
**Critérios de Sucesso:** {test_case.get('success_criteria', 'Critérios de sucesso')}

## INSTRUÇÕES PARA GERAÇÃO DE COMANDOS KUBERNETES
Com base no caso de teste e contexto apresentados, gere comandos kubectl específicos que devem:

1. **Executar o teste** conforme descrito no caso de teste
2. **Coletar métricas** durante a execução
3. **Monitorar o sistema** durante o teste
4. **Validar resultados** conforme critérios de sucesso
5. **Coletar logs** para análise posterior

### COMANDOS NECESSÁRIOS:
- Comandos para execução do teste
- Comandos para coleta de métricas
- Comandos para monitoramento
- Comandos para validação de resultados
- Comandos para coleta de logs

### FORMATO DE RESPOSTA:
Retorne apenas os comandos kubectl, um por linha, sem explicações adicionais."""

        # Coletar prompt gerado
        data_collector.collect_prompt(
            service_name="executor",
            prompt_type="kubectl_generation",
            prompt_content=kubectl_prompt,
            context=llm_context,
            metadata={
                "test_case": test_case,
                "experiment_id": context.get('experiment_id', 'Unknown')
            }
        )
        
        # Preparar dados da requisição
        llm_request_data = {
            "context": llm_context,
            "prompt": kubectl_prompt,
            "prompt_type": "kubectl_generation",
            "category": "executor_v10_2"
        }
        
        # Enviar requisição para LLM-Service
        response = requests.post(
            f"{LLM_SERVICE_URL}/generate-prompt",
            json=llm_request_data,
            timeout=120,  # Increased timeout for LLM operations
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            llm_response_data = response.json()
            generated_response = llm_response_data.get('response', '')
            
            # Coletar interação completa com LLM-Service
            data_collector.collect_llm_interaction(
                service_name="executor",
                request_data=llm_request_data,
                response_data=llm_response_data,
                metadata={
                    "test_case": test_case,
                    "experiment_id": context.get('experiment_id', 'Unknown'),
                    "prompt_type": "kubectl_generation"
                }
            )
            
            # Extrair comandos kubectl da resposta
            kubectl_commands = []
            lines = generated_response.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('kubectl') and line:
                    kubectl_commands.append(line)
            
            # Se não encontrou comandos, usar comandos padrão baseados no caso de teste
            if not kubectl_commands:
                kubectl_commands = test_case.get('kubectl_commands', [])
            
            # Coletar comandos kubectl gerados
            for command in kubectl_commands:
                data_collector.collect_kubernetes_command(
                    service_name="executor",
                    command=command,
                    expected_output="Comando gerado pelo LLM-Service",
                    metadata={
                        "test_case": test_case,
                        "experiment_id": context.get('experiment_id', 'Unknown')
                    }
                )
            
            return {
                'success': True,
                'kubectl_commands': kubectl_commands,
                'llm_response': generated_response,
                'llm_context': llm_context
            }
        else:
            logger.error(f"Erro no LLM-Service: {response.status_code}")
            return {
                'success': False,
                'kubectl_commands': test_case.get('kubectl_commands', []),
                'llm_response': 'LLM-Service não disponível',
                'llm_context': llm_context
            }
            
    except Exception as e:
        logger.error(f"Erro ao gerar comandos kubectl: {e}")
        return {
            'success': False,
            'kubectl_commands': test_case.get('kubectl_commands', []),
            'llm_response': f'Erro: {str(e)}',
            'llm_context': {}
        }

def validate_command_with_oracle(execution_result: Dict[str, Any], command: Dict[str, Any]) -> Dict[str, Any]:
    """Valida resultado do comando usando oracle"""
    try:
        success_criteria = command.get('success_criteria', '')
        failure_indicators = command.get('failure_indicators', '')
        expected_pattern = command.get('expected_output_pattern', '')
        oracle_validation = command.get('oracle_validation', '')
        
        # Verificar se o comando foi executado com sucesso
        command_success = execution_result.get('success', False)
        output = execution_result.get('stdout', '')
        error = execution_result.get('stderr', '')
        
        logger.info(f"Validando comando: {command.get('command', 'N/A')}")
        logger.info(f"Command success: {command_success}")
        logger.info(f"Output: {output[:100]}...")
        logger.info(f"Expected pattern: {expected_pattern}")
        logger.info(f"Oracle validation: {oracle_validation}")
        
        # Validação básica
        validation_result = {
            'command_executed': command_success,
            'output_received': bool(output),
            'error_detected': bool(error),
            'success': False,
            'validation_details': {}
        }
        
        if not command_success:
            validation_result['validation_details']['reason'] = 'Command execution failed'
            logger.warning(f"Command execution failed: {error}")
            return validation_result
        
        # Validação específica do oracle (prioritária)
        if oracle_validation:
            oracle_success = validate_oracle_specific(oracle_validation, output, execution_result)
            validation_result['validation_details']['oracle_validation'] = oracle_success
            logger.info(f"Oracle validation result: {oracle_success}")
            
            if oracle_success:
                validation_result['success'] = True
                validation_result['validation_details']['reason'] = 'Oracle validation passed'
                return validation_result
            else:
                validation_result['validation_details']['reason'] = f'Oracle validation failed: {oracle_validation}'
                return validation_result
        
        # Validar padrão esperado (fallback)
        if expected_pattern and output:
            import re
            pattern_match = re.search(expected_pattern, output, re.IGNORECASE)
            validation_result['validation_details']['pattern_match'] = bool(pattern_match)
            logger.info(f"Pattern match result: {bool(pattern_match)}")
            
            if pattern_match:
                validation_result['success'] = True
                validation_result['validation_details']['reason'] = 'Pattern validation passed'
                return validation_result
            else:
                validation_result['validation_details']['reason'] = f'Output does not match expected pattern: {expected_pattern}'
                return validation_result
        
        # Verificar indicadores de falha
        if failure_indicators and output:
            import re
            failure_match = re.search(failure_indicators, output, re.IGNORECASE)
            if failure_match:
                validation_result['validation_details']['reason'] = f'Failure indicator detected: {failure_match.group()}'
                return validation_result
        
        # Se chegou até aqui e tem output válido, considerar sucesso
        if output and len(output.strip()) > 0:
            validation_result['success'] = True
            validation_result['validation_details']['reason'] = 'Command executed successfully with output'
        else:
            validation_result['validation_details']['reason'] = 'No valid output received'
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Erro na validação do oracle: {e}")
        return {
            'command_executed': False,
            'output_received': False,
            'error_detected': True,
            'success': False,
            'validation_details': {'reason': f'Validation error: {str(e)}'}
        }

def get_expected_replicas() -> int:
    """Obtém o número esperado de réplicas do kube-znn dinamicamente"""
    try:
        # Tentar obter do environment variable primeiro
        env_replicas = os.getenv('TARGET_SYSTEM_REPLICAS')
        if env_replicas:
            return int(env_replicas)
        
        # Fallback: usar kubectl para obter replicas configuradas
        cmd = ["kubectl", "get", "deployment", "kube-znn", "-o", "jsonpath={.spec.replicas}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
        
        # Fallback final: usar valor padrão baseado na configuração atual
        logger.warning("Não foi possível obter replicas dinamicamente, usando fallback")
        return int(os.getenv('EXECUTOR_EXPECTED_REPLICAS', '5'))
        
    except Exception as e:
        logger.error(f"Erro ao obter expected replicas: {e}")
        return int(os.getenv('EXECUTOR_EXPECTED_REPLICAS', '5'))

def get_response_time_threshold() -> float:
    """Obtém o threshold de response time dinamicamente baseado em métricas reais"""
    try:
        # Tentar obter threshold configurável
        env_threshold = os.getenv('EXECUTOR_RESPONSE_TIME_THRESHOLD')
        if env_threshold:
            return float(env_threshold)
        
        # Fallback: usar threshold baseado em métricas históricas
        # Se não há métricas, usar valor conservador
        return float(os.getenv('EXECUTOR_RESPONSE_TIME_THRESHOLD', '200.0'))  # 200ms
        
    except Exception as e:
        logger.error(f"Erro ao obter response time threshold: {e}")
        return 200.0  # 200ms como fallback

def get_success_rate_threshold() -> float:
    """Obtém o threshold de success rate dinamicamente"""
    try:
        # Tentar obter threshold configurável
        env_threshold = os.getenv('EXECUTOR_SUCCESS_RATE_THRESHOLD')
        if env_threshold:
            return float(env_threshold)
        
        # Fallback: usar threshold baseado em métricas históricas
        return float(os.getenv('EXECUTOR_SUCCESS_RATE_THRESHOLD', '95.0'))  # 95%
        
    except Exception as e:
        logger.error(f"Erro ao obter success rate threshold: {e}")
        return 95.0  # 95% como fallback

def validate_oracle_specific(oracle_validation: str, output: str, execution_result: Dict[str, Any]) -> bool:
    """Validação específica baseada no oracle"""
    try:
        oracle_lower = oracle_validation.lower()
        logger.info(f"Validando oracle específico: {oracle_validation}")
        
        # Validação de contagem de pods
        if 'count running' in oracle_lower:
            running_count = output.count('Running')
            expected_replicas = get_expected_replicas()
            logger.info(f"Running pods count: {running_count}, expected: {expected_replicas}")
            return running_count >= expected_replicas
        
        # Validação de tempo de resposta
        elif 'time value' in oracle_lower:
            import re
            time_match = re.search(r'(\d+\.?\d*)', output)
            if time_match:
                time_value = float(time_match.group(1))
                response_time_threshold = get_response_time_threshold()
                logger.info(f"Time value: {time_value}ms, threshold: {response_time_threshold}ms")
                return time_value < response_time_threshold
        
        # Validação de status HTTP
        elif 'http status' in oracle_lower:
            http_success = '200' in output or 'HTTP/1.1 200' in output or 'healthy' in output.lower()
            logger.info(f"HTTP status validation: {http_success}")
            return http_success
        
        # Validação de ClusterIP ou NodePort
        elif 'clusterip' in oracle_lower:
            service_success = ('ClusterIP' in output or 'NodePort' in output) and 'kube-znn' in output
            logger.info(f"Service validation (ClusterIP/NodePort): {service_success}")
            return service_success
        
        # Validação de taxa de sucesso
        elif 'success rate' in oracle_lower:
            import re
            success_match = re.search(r'(\d+\.?\d*)%', output)
            if success_match:
                success_rate = float(success_match.group(1))
                success_rate_threshold = get_success_rate_threshold()
                logger.info(f"Success rate: {success_rate}%, threshold: {success_rate_threshold}%")
                return success_rate >= success_rate_threshold
        
        # Validação de pods esperados
        elif 'expected replicas' in oracle_lower:
            running_count = output.count('Running')
            logger.info(f"Expected replicas validation: {running_count} running pods")
            return running_count >= 1  # Pelo menos 1 pod rodando
        
        # Validação de service points to running pods
        elif 'service points to running pods' in oracle_lower:
            has_service = 'kube-znn' in output and ('ClusterIP' in output or 'NodePort' in output)
            logger.info(f"Service points to pods validation: {has_service}")
            return has_service
        
        # Validação padrão - verificar se há output válido
        else:
            has_output = bool(output and len(output.strip()) > 0)
            logger.info(f"Default validation (has output): {has_output}")
            return has_output
        
        return False
        
    except Exception as e:
        logger.error(f"Erro na validação específica do oracle: {e}")
        return False

def generate_detailed_command_description(command: str) -> str:
    """Generate detailed English description of what the kubectl command does"""
    command_lower = command.lower()
    
    # Response time measurement commands
    if "curl -w '%{time_total}'" in command_lower:
        if "monitor" in command_lower:
            return "Measures response time from Monitor pod to ZNN service endpoint. Uses curl with time_total format to capture precise latency measurements in seconds. This command tests network connectivity and response performance from the monitoring component."
        elif "analyzer" in command_lower:
            return "Measures response time from Analyzer pod to ZNN service endpoint. Uses curl with time_total format to capture precise latency measurements in seconds. This command tests network connectivity and response performance from the analysis component."
        elif "planner" in command_lower:
            return "Measures response time from Planner pod to ZNN service endpoint. Uses curl with time_total format to capture precise latency measurements in seconds. This command tests network connectivity and response performance from the planning component."
        elif "localhost:8080" in command_lower:
            return "Measures internal response time within ZNN pod itself. Uses curl with time_total format to capture precise latency measurements in seconds. This command tests the internal performance of the ZNN application without network overhead."
        else:
            return "Measures response time to ZNN service endpoint. Uses curl with time_total format to capture precise latency measurements in seconds. This command tests network connectivity and response performance."
    
    # Load testing commands
    elif "ab -n" in command_lower and "ab -c" in command_lower:
        if "monitor" in command_lower:
            return "Performs load testing from Monitor pod to ZNN service using Apache Bench (ab). Sends multiple concurrent requests to test system capacity and performance under load. This command simulates high traffic conditions to evaluate system stability."
        elif "analyzer" in command_lower:
            return "Performs load testing from Analyzer pod to ZNN service using Apache Bench (ab). Sends multiple concurrent requests to test system capacity and performance under load. This command simulates high traffic conditions to evaluate system stability."
        else:
            return "Performs load testing to ZNN service using Apache Bench (ab). Sends multiple concurrent requests to test system capacity and performance under load. This command simulates high traffic conditions to evaluate system stability."
    
    # Pod status commands
    elif "kubectl get pods" in command_lower:
        if "-o wide" in command_lower:
            return "Retrieves detailed status information of ZNN pods including IP addresses, nodes, and readiness states. Uses wide output format to display comprehensive pod information for connectivity verification and troubleshooting."
        else:
            return "Retrieves current status of ZNN pods including their state (Running, Pending, Error) and readiness indicators. This command verifies that all ZNN pods are healthy and accessible."
    
    # Service commands
    elif "kubectl get service" in command_lower:
        return "Retrieves ZNN service configuration including ClusterIP, ports, and endpoints. This command verifies that the ZNN service is properly configured and accessible within the Kubernetes cluster."
    
    # Resource monitoring commands
    elif "kubectl top pods" in command_lower:
        return "Monitors real-time resource usage (CPU and memory) of ZNN pods. This command provides current resource consumption metrics to assess system performance and identify potential bottlenecks during testing."
    
    # Pod description commands
    elif "kubectl describe pods" in command_lower:
        return "Provides detailed information about ZNN pods including events, conditions, and resource specifications. This command helps diagnose issues and verify pod configuration during testing."
    
    # Scaling commands
    elif "kubectl scale" in command_lower:
        return "Modifies the number of ZNN pod replicas to test scaling behavior. This command evaluates the system's ability to handle increased load by adjusting the number of running instances."
    
    # Default description
    else:
        return f"Executes kubectl command: {command}. This command performs Kubernetes cluster operations for testing and validation purposes."

def execute_kubectl_command(command: str) -> Dict[str, Any]:
    """Executa comando kubectl e retorna resultado"""
    try:
        # Generate detailed description
        detailed_description = generate_detailed_command_description(command)
        
        # Executar comando kubectl usando shell=True para comandos complexos
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout for kubectl commands
        )
        
        execution_result = {
            'command': command,
            'detailed_description': detailed_description,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Coletar resultado da execução
        data_collector = get_data_collector()
        data_collector.collect_kubernetes_result(
            service_name="executor",
            command=command,
            result=execution_result,
            success=result.returncode == 0,
            metadata={
                "execution_timestamp": datetime.now().isoformat()
            }
        )
        
        return execution_result
        
    except subprocess.TimeoutExpired:
        return {
            'command': command,
            'returncode': -1,
            'stdout': '',
            'stderr': 'Timeout expired',
            'success': False,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'command': command,
            'returncode': -1,
            'stdout': '',
            'stderr': str(e),
            'success': False,
            'timestamp': datetime.now().isoformat()
        }

# @app.post("/generate-kubectl-commands", response_model=KubectlCommandResponse)
# async def generate_kubectl_commands(request: KubectlExecutionRequest):
#     """Gera comandos kubectl para um caso de teste específico"""
#     try:
#         logger.info(f"Gerando comandos kubectl para caso de teste {request.test_case.get('id', 'TC001')}")
#         
#         # Gerar comandos kubectl via LLM-Service
#         result = generate_kubectl_commands_via_llm(request.test_case, request.context)
#         
#         return KubectlCommandResponse(
#             experiment_id=request.experiment_id,
#             test_case_id=request.test_case.get('id', 'TC001'),
#             generated_commands=result['kubectl_commands'],
#             llm_response=result['llm_response'],
#             timestamp=datetime.now().isoformat()
#         )
#         
#     except Exception as e:
#         logger.error(f"Erro ao gerar comandos kubectl: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute", response_model=KubectlExecutionResponse)
async def execute_kubectl_commands(request: KubectlExecutionRequest):
    """Executa comandos kubectl buscados do Knowledge"""
    global executor_logger
    
    try:
        # Inicializar logger se não existir
        if executor_logger is None:
            executor_logger = ExecutorLogger(request.experiment_id, request.run_id)
        
        logger.info(f"Executando comandos kubectl para experimento {request.experiment_id}")
        
        # Log do início da execução
        executor_logger.log_execution_start(request.dict())
        
        # BUSCAR COMANDOS DO KNOWLEDGE
        logger.info("Buscando comandos kubectl do Knowledge...")
        planner_data = await get_planner_data_from_knowledge(request.experiment_id)
        
        if not planner_data or 'kubectl_commands' not in planner_data:
            logger.warning("Nenhum comando kubectl encontrado no Knowledge, usando comandos da requisição")
            kubectl_commands = request.kubectl_commands or []
        else:
            kubectl_commands = planner_data['kubectl_commands']
            logger.info(f"Encontrados {len(kubectl_commands)} comandos kubectl no Knowledge")
        
        # Se não há comandos, criar comandos padrão
        if not kubectl_commands:
            logger.warning("Nenhum comando encontrado, criando comandos padrão")
            kubectl_commands = [
                {
                    "id": "cmd_1",
                    "command": "kubectl get pods -n default -l app=kube-znn",
                    "description": "Verify ZNN pod status",
                    "expected_output_pattern": "Running.*Ready.*2/2",
                    "success_criteria": "All ZNN pods in Running state",
                    "failure_indicators": "CrashLoopBackOff|Error|Pending",
                    "oracle_validation": "Count Running ZNN pods = expected replicas"
                },
                {
                    "id": "cmd_2",
                    "command": "kubectl get service kube-znn -n default",
                    "description": "Verify ZNN service endpoints",
                    "expected_output_pattern": "kube-znn.*(ClusterIP|NodePort)",
                    "success_criteria": "ZNN service has valid ClusterIP or NodePort",
                    "failure_indicators": "No service or invalid IP",
                    "oracle_validation": "ZNN service points to running pods"
                }
            ]
        
        executed_commands = []
        execution_results = []
        test_case_results = []
        
        # Executar cada comando kubectl
        for i, command in enumerate(kubectl_commands):
            logger.info(f"Executando comando {i+1}: {command.get('command', 'N/A')}")
            
            # Executar o comando kubectl
            execution_result = execute_kubectl_command(command.get('command', ''))
            
            # Validar resultado usando oracle
            oracle_result = validate_command_with_oracle(execution_result, command)
            
            # Criar resultado completo
            complete_result = {
                'command_id': command.get('id', f'cmd_{i+1}'),
                'command': command.get('command', ''),
                'description': command.get('description', ''),
                'detailed_description': execution_result.get('detailed_description', ''),
                'execution_result': execution_result,
                'oracle_validation': oracle_result,
                'success': oracle_result['success'],
                'timestamp': datetime.now().isoformat()
            }
            
            executed_commands.append(command)
            execution_results.append(complete_result)
            
            # Log detailed execution information
            logger.info(f"=== COMMAND {i+1} EXECUTION DETAILS ===")
            logger.info(f"Command ID: {complete_result['command_id']}")
            logger.info(f"Command: {complete_result['command']}")
            logger.info(f"Description: {complete_result['description']}")
            logger.info(f"Detailed Description: {complete_result['detailed_description']}")
            logger.info(f"Execution Success: {complete_result['success']}")
            logger.info(f"Oracle Validation: {oracle_result['success']}")
            logger.info(f"Return Code: {execution_result['returncode']}")
            logger.info(f"Output Length: {len(execution_result['stdout'])} characters")
            if execution_result['stderr']:
                logger.info(f"Error Output: {execution_result['stderr']}")
            logger.info("=== END COMMAND DETAILS ===")
        
        # Processar resultados por caso de teste
        for test_case in request.test_cases:
            test_case_id = test_case.get('id', 'unknown')
            test_case_commands = [cmd for cmd in execution_results if cmd['command_id'].startswith(test_case_id.split('_')[0])]
            
            test_case_result = {
                'test_case_id': test_case_id,
                'test_case_name': test_case.get('name', 'Unknown'),
                'commands_executed': len(test_case_commands),
                'commands_successful': len([cmd for cmd in test_case_commands if cmd['success']]),
                'success': all(cmd['success'] for cmd in test_case_commands) if test_case_commands else True,
                'execution_details': test_case_commands,
                'timestamp': datetime.now().isoformat()
            }
            
            test_case_results.append(test_case_result)
        
        # Determinar sucesso geral
        overall_success = all(result['success'] for result in execution_results) if execution_results else True
        
        # Criar resposta
        response = KubectlExecutionResponse(
            experiment_id=request.experiment_id,
            run_id=request.run_id,
            executed_commands=executed_commands,
            execution_results=execution_results,
            test_case_results=test_case_results,
            timestamp=datetime.now().isoformat(),
            success=overall_success
        )
        
        # Coletar dados
        try:
            data_collector = get_data_collector(request.experiment_id)
            data_collector.collect_execution_result(
                service_name="executor",
                execution_data=response.dict(),
                metadata={
                    "experiment_id": request.experiment_id,
                    "total_commands": len(executed_commands),
                    "overall_success": overall_success
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao coletar dados: {e}")
        
        # NOVA FUNCIONALIDADE: Armazenar resultados no Knowledge Service
        await store_execution_results_in_knowledge(request.experiment_id, request.run_id, response)
        
        # NOVA FUNCIONALIDADE: Salvar executor.json para coletas futuras
        await save_executor_json_for_future_collection(request.experiment_id, request.run_id, response)
        
        logger.info(f"Execução concluída para {request.experiment_id}: {overall_success}")
        return response
        
    except Exception as e:
        logger.error(f"Erro na execução de comandos kubectl: {e}")
        # Retornar resposta de erro em vez de levantar exceção
        return KubectlExecutionResponse(
            experiment_id=request.experiment_id,
            run_id=request.run_id,
            executed_commands=[],
            execution_results=[],
            test_case_results=[],
            timestamp=datetime.now().isoformat(),
            success=False
        )

async def get_planner_data_from_knowledge(experiment_id: str) -> Dict[str, Any]:
    """Obtém dados do Planner do Knowledge Service"""
    try:
        logger.info(f"Buscando dados do Planner no Knowledge para experimento {experiment_id}")
        knowledge_response = requests.get(f"{KNOWLEDGE_URL}/data-collection/{experiment_id}", timeout=10)
        
        if knowledge_response.status_code == 200:
            data = knowledge_response.json()
            logger.info(f"Dados do Knowledge obtidos: {len(data.get('entries', []))} entradas")
            
            # Buscar dados do Planner nas entradas
            planner_data = {}
            for entry in data.get('entries', []):
                if entry.get('source_service') == 'planner':
                    planner_data = entry.get('data', {})
                    logger.info(f"Dados do Planner encontrados: {len(planner_data.get('kubectl_commands', []))} comandos")
                    break
            
            return planner_data
        else:
            logger.warning(f"Falha ao buscar dados do Knowledge: {knowledge_response.status_code} - {knowledge_response.text}")
            return {}
    except Exception as e:
        logger.error(f"Erro ao obter dados do Knowledge: {e}")
        return {}

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

@app.post("/execute-test-cases", response_model=TestCaseResponse)
async def execute_test_cases(request: TestCaseRequest):
    """Executa casos de teste enviando para LLM-Service e executando comandos kubectl"""
    try:
        logger.info(f"Executando {len(request.test_cases)} casos de teste para experimento {request.experiment_id}")
        
        # Obter dados do monitor do Knowledge
        monitor_data = await get_monitor_data_from_knowledge()
        logger.info(f"Dados do monitor obtidos: {len(monitor_data)} campos")
        
        executed_test_cases = []
        kubectl_commands = []
        execution_results = []
        
        for test_case in request.test_cases:
            logger.info(f"Processando caso de teste: {test_case.get('id', 'TC001')}")
            
            # 1. Gerar comandos kubectl via LLM-Service com dados do monitor
            kubectl_result = generate_kubectl_commands_via_llm(test_case, {
                'experiment_id': request.experiment_id,
                'analysis_context': request.analysis_context,
                'planning_context': request.planning_context,
                'monitor_data': monitor_data  # Incluir dados do monitor
            })
            
            # 2. Executar comandos kubectl gerados
            test_case_results = []
            for command in kubectl_result['kubectl_commands']:
                logger.info(f"Executando comando: {command}")
                execution_result = execute_kubectl_command(command)
                test_case_results.append(execution_result)
                execution_results.append(execution_result)
            
            # 3. Coletar resultados do caso de teste
            executed_test_case = {
                'test_case': test_case,
                'kubectl_commands': kubectl_result['kubectl_commands'],
                'llm_response': kubectl_result['llm_response'],
                'execution_results': test_case_results,
                'success': all(r['success'] for r in test_case_results),
                'timestamp': datetime.now().isoformat()
            }
            
            # Coletar caso de teste executado
            try:
                data_collector.collect_test_case(
                    service_name="executor",
                    test_case=executed_test_case,
                    metadata={
                        "experiment_id": request.experiment_id,
                        "execution_timestamp": datetime.now().isoformat()
                    }
                )
            except Exception as e:
                logger.warning(f"Erro ao coletar caso de teste: {e}")
            
            executed_test_cases.append(executed_test_case)
            kubectl_commands.extend(kubectl_result['kubectl_commands'])
        
        # 4. Determinar sucesso geral
        overall_success = all(tc['success'] for tc in executed_test_cases)
        
        # Criar resposta final
        response = TestCaseResponse(
            experiment_id=request.experiment_id,
            executed_test_cases=executed_test_cases,
            kubectl_commands=kubectl_commands,
            execution_results=execution_results,
            timestamp=datetime.now().isoformat(),
            success=overall_success
        )
        
        # Coletar resultado final da execução
        data_collector = get_data_collector(request.experiment_id)
        data_collector.collect_execution_result(
            service_name="executor",
            execution_data=response.dict(),
            metadata={
                "experiment_id": request.experiment_id,
                "total_test_cases": len(executed_test_cases),
                "total_commands": len(kubectl_commands),
                "overall_success": overall_success
            }
        )
        
        # Salvar resultado no Knowledge Service
        try:
            knowledge_data = {
                "execution_result": response.dict(),
                "source": "executor_service",
                "timestamp": datetime.now().isoformat(),
                "experiment_id": request.experiment_id
            }
            
            # Coletar mensagem para o Knowledge
            data_collector.collect_message(
                message_type=MessageType.EXECUTOR_TO_KNOWLEDGE,
                source_service="executor",
                target_service="knowledge",
                message_data=knowledge_data,
                metadata={
                    "total_test_cases": len(executed_test_cases),
                    "overall_success": overall_success
                }
            )
            
        except Exception as e:
            logger.error(f"Erro ao salvar resultado no Knowledge: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Erro ao executar casos de teste: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "executor", "version": "v10.3"}

async def store_execution_results_in_knowledge(experiment_id: str, run_id: str, response: KubectlExecutionResponse):
    """Armazena resultados da execução no Knowledge Service"""
    try:
        logger.info(f"Armazenando resultados da execução no Knowledge para experimento {experiment_id}")
        
        # Preparar dados para armazenamento
        execution_data = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "execution_timestamp": response.timestamp,
            "success": response.success,
            "executed_commands": response.executed_commands,
            "execution_results": response.execution_results,
            "test_case_results": response.test_case_results,
            "summary": {
                "total_commands": len(response.executed_commands),
                "successful_commands": sum(1 for r in response.execution_results if r['success']),
                "failed_commands": sum(1 for r in response.execution_results if not r['success']),
                "success_rate": (sum(1 for r in response.execution_results if r['success']) / len(response.execution_results) * 100) if response.execution_results else 0,
                "oracle_validations_passed": sum(1 for r in response.execution_results if r.get('oracle_validation', {}).get('success', False)),
                "oracle_validations_failed": sum(1 for r in response.execution_results if not r.get('oracle_validation', {}).get('success', True)),
                "overall_success": response.success
            },
            "detailed_descriptions": {
                "commands_with_descriptions": [
                    {
                        "command_id": cmd.get('id', ''),
                        "command": cmd.get('command', ''),
                        "description": cmd.get('description', ''),
                        "detailed_description": cmd.get('detailed_description', '')
                    }
                    for cmd in response.executed_commands
                ]
            },
            "source": "executor_service",
            "service_version": "v10.3"
        }
        
        # Enviar para Knowledge Service
        knowledge_url = f"{KNOWLEDGE_URL}/execution-results/{experiment_id}"
        knowledge_response = requests.post(
            knowledge_url,
            json=execution_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if knowledge_response.status_code == 200:
            logger.info(f"✅ Resultados da execução armazenados no Knowledge para {experiment_id}")
        else:
            logger.warning(f"⚠️ Falha ao armazenar no Knowledge: {knowledge_response.status_code} - {knowledge_response.text}")
            
    except Exception as e:
        logger.error(f"❌ Erro ao armazenar resultados no Knowledge: {str(e)}")

async def save_executor_json_for_future_collection(experiment_id: str, run_id: str, response: KubectlExecutionResponse):
    """Salva executor.json para coletas futuras"""
    try:
        logger.info(f"Salvando executor.json para coleta futura do experimento {experiment_id}")
        
        # Criar estrutura JSON para arquivo executor.json
        executor_json_data = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "execution_timestamp": response.timestamp,
            "source": "executor_service_direct_execution",
            "test_type": "execution_complete",
            "executed_commands": response.executed_commands,
            "execution_results": response.execution_results,
            "test_case_results": response.test_case_results,
            "summary": {
                "total_commands": len(response.executed_commands),
                "successful_commands": sum(1 for r in response.execution_results if r['success']),
                "failed_commands": sum(1 for r in response.execution_results if not r['success']),
                "success_rate": (sum(1 for r in response.execution_results if r['success']) / len(response.execution_results) * 100) if response.execution_results else 0,
                "oracle_validations_passed": sum(1 for r in response.execution_results if r.get('oracle_validation', {}).get('success', False)),
                "oracle_validations_failed": sum(1 for r in response.execution_results if not r.get('oracle_validation', {}).get('success', True)),
                "overall_success": response.success
            },
            "detailed_descriptions": {
                "commands_with_descriptions": [
                    {
                        "command_id": cmd.get('id', ''),
                        "command": cmd.get('command', ''),
                        "description": cmd.get('description', ''),
                        "detailed_description": cmd.get('detailed_description', '')
                    }
                    for cmd in response.executed_commands
                ]
            },
            "logs_preview": f"Executor data: {len(response.executed_commands)} commands executed, {sum(1 for r in response.execution_results if r['success'])} successful",
            "service_version": "v10.3"
        }
        
        # Salvar em arquivo temporário para coleta futura
        import tempfile
        import os
        
        # Criar diretório temporário se não existir
        temp_dir = "/tmp/executor_data"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Salvar arquivo JSON
        json_file_path = f"{temp_dir}/executor_{experiment_id}_{run_id}.json"
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(executor_json_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ executor.json salvo em {json_file_path} para coleta futura")
        
        # Também salvar no Redis para acesso rápido
        try:
            redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
            redis_key = f"executor_data:{experiment_id}:{run_id}"
            redis_client.setex(redis_key, 3600, json.dumps(executor_json_data))  # Expira em 1 hora
            logger.info(f"✅ Dados também salvos no Redis com chave {redis_key}")
        except Exception as redis_error:
            logger.warning(f"⚠️ Erro ao salvar no Redis: {redis_error}")
            
    except Exception as e:
        logger.error(f"❌ Erro ao salvar executor.json: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Executor Service",
        "version": "v10.3",
        "description": "Microserviço para execução de casos de teste via LLM-Service com armazenamento completo",
        "endpoints": {
            "/generate-kubectl-commands": "Gera comandos kubectl para caso de teste",
            "/execute-test-cases": "Executa casos de teste completos",
            "/execute-kubectl-commands": "Executa comandos kubectl com armazenamento completo",
            "/health": "Health check"
        },
        "features": {
            "knowledge_storage": "Armazena resultados no Knowledge Service",
            "executor_json": "Salva executor.json para coletas futuras",
            "detailed_descriptions": "Gera descrições detalhadas dos comandos",
            "oracle_validation": "Validação Oracle completa"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)