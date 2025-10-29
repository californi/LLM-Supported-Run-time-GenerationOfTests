# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Service", version="1.0.0")

# Configuração Redis
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# Categorias de Prompts (Persistidas no Knowledge)
PROMPT_CATEGORIES = {
    'reachability': {
        'name': 'Teste de Alcançabilidade',
        'description': 'Prompts para gerar casos de teste que verificam se todos os pods estão acessíveis e respondendo',
        'prompts': [
            'Gere casos de teste para verificar se todos os pods kube-znn estão acessíveis via HTTP',
            'Crie testes de conectividade para validar a alcançabilidade de cada pod individualmente',
            'Desenvolva casos de teste para verificar se o serviço kube-znn responde em todas as rotas'
        ]
    },
    'response_time': {
        'name': 'Teste de Tempo de Resposta',
        'description': 'Prompts para gerar casos de teste que medem e validam o tempo de resposta do sistema',
        'prompts': [
            'Gere casos de teste para medir o tempo de resposta das requisições ao kube-znn',
            'Crie testes de performance que validem se o tempo de resposta está dentro dos SLAs',
            'Desenvolva casos de teste para verificar latência sob diferentes cargas'
        ]
    },
    'load': {
        'name': 'Teste de Carga',
        'description': 'Prompts para gerar casos de teste de carga e stress do sistema',
        'prompts': [
            'Gere casos de teste de carga para verificar comportamento do sistema sob alta demanda',
            'Crie testes de stress que avaliem o limite de capacidade do kube-znn',
            'Desenvolva casos de teste para validar escalabilidade e degradação graceful'
        ]
    }
}

# Qualidades de mídia suportadas
MEDIA_QUALITIES = ['400kb', '600kb', '800kb']

# Inicializar categorias de prompts no Redis (na primeira execução)
@app.on_event("startup")
async def initialize_knowledge():
    """Inicializa conhecimento base no Redis"""
    try:
        # Persistir categorias de prompts
        redis_client.set('knowledge:prompt_categories', json.dumps(PROMPT_CATEGORIES))
        
        # Persistir qualidades de mídia
        redis_client.set('knowledge:media_qualities', json.dumps(MEDIA_QUALITIES))
        
        print("Knowledge base initialized successfully")
    except Exception as e:
        print(f"Error initializing knowledge: {e}")

# Models
class ServerInfo(BaseModel):
    pod_name: str
    namespace: str
    status: str
    cpu: str
    memory: str
    image: str
    timestamp: str

class MonitorData(BaseModel):
    servers: List[Dict[str, Any]]
    media_quality: str
    server_load: Dict[str, Any]
    timestamp: str

class PromptSelection(BaseModel):
    category: str
    selected_prompts: List[str]
    health_criterion: str
    timestamp: str

class PriorityInfo(BaseModel):
    cpu_available: int
    memory_available: int
    previous_config: Dict[str, Any]
    health_criterion: str
    timestamp: str

class TestCase(BaseModel):
    test_id: str
    name: str
    type: str
    description: str
    criterion: str
    expected: str
    command: str
    oracle: str

class TestReport(BaseModel):
    experiment_id: int
    total_tests: int
    passed: int
    failed: int
    test_results: List[Dict[str, Any]]
    comparisons: List[Dict[str, Any]]
    timestamp: str

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "knowledge", "timestamp": datetime.now().isoformat()}

# 1. Servidores (PODs kube-znn)
@app.post("/servers")
async def store_servers(servers: List[Dict[str, Any]]):
    """Armazena informações dos servidores/pods"""
    try:
        key = f'knowledge:servers:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(servers))
        redis_client.lpush('knowledge:servers:all', key)
        return {"status": "stored", "key": key, "count": len(servers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/servers")
async def get_servers():
    """Retorna informações dos servidores"""
    try:
        keys = redis_client.lrange('knowledge:servers:all', 0, 0)
        if keys:
            data = redis_client.get(keys[0])
            if data:
                return {"servers": json.loads(data)}
        return {"servers": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Qualidade de mídia
@app.get("/media-qualities")
async def get_media_qualities():
    """Retorna qualidades de mídia suportadas"""
    try:
        data = redis_client.get('knowledge:media_qualities')
        if data:
            return {"media_qualities": json.loads(data)}
        return {"media_qualities": MEDIA_QUALITIES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Categorias de prompts
@app.get("/prompt-categories")
async def get_prompt_categories():
    """Retorna categorias de prompts persistidas"""
    try:
        data = redis_client.get('knowledge:prompt_categories')
        if data:
            return {"categories": json.loads(data)}
        return {"categories": PROMPT_CATEGORIES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prompt-categories/{category}")
async def get_prompt_category(category: str):
    """Retorna uma categoria específica de prompts"""
    try:
        data = redis_client.get('knowledge:prompt_categories')
        if data:
            categories = json.loads(data)
            if category in categories:
                return {"category": category, "data": categories[category]}
        raise HTTPException(status_code=404, detail=f"Category {category} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Prompts selecionados (na etapa Monitor/Analyzer)
@app.post("/selected-prompts")
async def store_selected_prompts(selection: Dict[str, Any]):
    """Armazena prompts selecionados"""
    try:
        key = f'knowledge:selected_prompts:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(selection))
        redis_client.set('knowledge:selected_prompts:current', json.dumps(selection))
        redis_client.lpush('knowledge:selected_prompts:all', key)
        return {"status": "stored", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/selected-prompts")
async def get_selected_prompts():
    """Retorna prompts selecionados"""
    try:
        data = redis_client.get('knowledge:selected_prompts:current')
        if data:
            return json.loads(data)
        raise HTTPException(status_code=404, detail="No selected prompts available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Critérios de prioridade (na etapa Planner)
@app.post("/priority-criteria")
async def store_priority_criteria(criteria: Dict[str, Any]):
    """Armazena critérios de prioridade do Planner"""
    try:
        key = f'knowledge:priority:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(criteria))
        redis_client.set('knowledge:priority:current', json.dumps(criteria))
        redis_client.lpush('knowledge:priority:all', key)
        return {"status": "stored", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/priority-criteria")
async def get_priority_criteria():
    """Retorna critérios de prioridade"""
    try:
        data = redis_client.get('knowledge:priority:current')
        if data:
            return json.loads(data)
        return {"cpu_available": 0, "memory_available": 0, "previous_config": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Casos de teste a serem executados (na etapa Executor)
@app.post("/test-cases")
async def store_test_cases(test_cases: List[Dict[str, Any]]):
    """Armazena casos de teste a serem executados"""
    try:
        key = f'knowledge:test_cases:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(test_cases))
        redis_client.set('knowledge:test_cases:current', json.dumps(test_cases))
        redis_client.lpush('knowledge:test_cases:all', key)
        return {"status": "stored", "key": key, "count": len(test_cases)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-cases")
async def get_test_cases():
    """Retorna casos de teste a serem executados"""
    try:
        data = redis_client.get('knowledge:test_cases:current')
        if data:
            return {"test_cases": json.loads(data)}
        raise HTTPException(status_code=404, detail="No test cases available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Relatório de teste (na etapa Executor)
@app.post("/test-report")
async def store_test_report(report: Dict[str, Any]):
    """Armazena relatório de teste"""
    try:
        key = f'knowledge:test_report:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(report))
        redis_client.set('knowledge:test_report:current', json.dumps(report))
        redis_client.lpush('knowledge:test_report:all', key)
        
        # Manter histórico para comparações
        redis_client.lpush('knowledge:test_report:history', json.dumps(report))
        
        return {"status": "stored", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-report")
async def get_test_report():
    """Retorna relatório de teste atual"""
    try:
        data = redis_client.get('knowledge:test_report:current')
        if data:
            return json.loads(data)
        raise HTTPException(status_code=404, detail="No test report available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-report/history")
async def get_test_report_history(limit: int = 10):
    """Retorna histórico de relatórios para comparação"""
    try:
        reports = redis_client.lrange('knowledge:test_report:history', 0, limit - 1)
        history = [json.loads(r) for r in reports]
        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para dados do Monitor
@app.post("/monitor-data")
async def store_monitor_data(data: Dict[str, Any]):
    """Armazena dados coletados pelo Monitor"""
    try:
        key = f'knowledge:monitor:{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        redis_client.set(key, json.dumps(data))
        redis_client.set('knowledge:monitor:current', json.dumps(data))
        redis_client.lpush('knowledge:monitor:all', key)
        return {"status": "stored", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/monitor-data")
async def get_monitor_data():
    """Retorna dados do Monitor"""
    try:
        current_data = redis_client.get('knowledge:monitor:current')
        if current_data:
            return json.loads(current_data)
        return {"status": "no_data"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para dados de coleta detalhada
@app.post("/data-collection")
async def store_data_collection_entry(entry: Dict[str, Any]):
    """Armazena entrada de coleta de dados detalhada"""
    try:
        entry_id = entry.get('entry_id', f"entry_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
        key = f'knowledge:data_collection:{entry_id}'
        redis_client.set(key, json.dumps(entry))
        
        # Adicionar à lista do experimento
        experiment_id = entry.get('experiment_id', 'unknown')
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        redis_client.lpush(experiment_list_key, entry_id)
        
        # Manter apenas os últimos 1000 entries por experimento
        redis_client.ltrim(experiment_list_key, 0, 999)
        
        return {"status": "stored", "entry_id": entry_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# NOVO ENDPOINT: Armazenar resultados de execução do Executor
@app.post("/execution-results/{experiment_id}")
async def store_execution_results(experiment_id: str, execution_data: Dict[str, Any]):
    """Armazena resultados completos da execução do Executor"""
    try:
        logger.info(f"Armazenando resultados de execução para experimento {experiment_id}")
        
        # Adicionar metadados
        execution_data['stored_timestamp'] = datetime.now().isoformat()
        execution_data['experiment_id'] = experiment_id
        
        # Armazenar no Redis com chave específica
        key = f'knowledge:execution_results:{experiment_id}'
        redis_client.set(key, json.dumps(execution_data))
        
        # Também adicionar à lista de execuções do experimento
        execution_list_key = f'knowledge:experiment:{experiment_id}:executions'
        execution_timestamp = execution_data.get('execution_timestamp', datetime.now().isoformat())
        redis_client.lpush(execution_list_key, execution_timestamp)
        
        # Manter apenas os últimos 100 execuções por experimento
        redis_client.ltrim(execution_list_key, 0, 99)
        
        # Armazenar também por timestamp para busca temporal
        timestamp_key = f'knowledge:execution_results:{experiment_id}:{execution_timestamp}'
        redis_client.set(timestamp_key, json.dumps(execution_data))
        
        logger.info(f"✅ Resultados de execução armazenados para {experiment_id}")
        return {
            "status": "stored", 
            "experiment_id": experiment_id,
            "execution_timestamp": execution_timestamp,
            "total_commands": execution_data.get('summary', {}).get('total_commands', 0),
            "success_rate": execution_data.get('summary', {}).get('success_rate', 0)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao armazenar resultados de execução: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/execution-results/{experiment_id}")
async def get_execution_results(experiment_id: str):
    """Retorna resultados de execução para um experimento"""
    try:
        key = f'knowledge:execution_results:{experiment_id}'
        execution_data = redis_client.get(key)
        
        if execution_data:
            return json.loads(execution_data)
        else:
            return {"error": "No execution results found for this experiment"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/execution-results/{experiment_id}/history")
async def get_execution_history(experiment_id: str, limit: int = 10):
    """Retorna histórico de execuções para um experimento"""
    try:
        execution_list_key = f'knowledge:experiment:{experiment_id}:executions'
        execution_timestamps = redis_client.lrange(execution_list_key, 0, limit - 1)
        
        executions = []
        for timestamp in execution_timestamps:
            timestamp_key = f'knowledge:execution_results:{experiment_id}:{timestamp}'
            execution_data = redis_client.get(timestamp_key)
            if execution_data:
                executions.append(json.loads(execution_data))
        
        return {
            "experiment_id": experiment_id,
            "executions": executions,
            "total_executions": len(executions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}")
async def get_data_collection_entries(experiment_id: str, limit: int = 100):
    """Retorna entradas de coleta de dados para um experimento"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, limit - 1)
        
        entries = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entries.append(json.loads(entry_data))
        
        return {
            "experiment_id": experiment_id,
            "total_entries": len(entries),
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/by-type/{data_type}")
async def get_data_collection_by_type(experiment_id: str, data_type: str, limit: int = 50):
    """Retorna entradas de coleta de dados por tipo"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        entries = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entry = json.loads(entry_data)
                if entry.get('data_type') == data_type:
                    entries.append(entry)
                    if len(entries) >= limit:
                        break
        
        return {
            "experiment_id": experiment_id,
            "data_type": data_type,
            "total_entries": len(entries),
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/messages/{message_type}")
async def get_messages_by_type(experiment_id: str, message_type: str, limit: int = 50):
    """Retorna mensagens por tipo específico"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        messages = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entry = json.loads(entry_data)
                if (entry.get('data_type') == 'message' and 
                    entry.get('message_type') == message_type):
                    messages.append(entry)
                    if len(messages) >= limit:
                        break
        
        return {
            "experiment_id": experiment_id,
            "message_type": message_type,
            "total_messages": len(messages),
            "messages": messages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/llm-interactions")
async def get_llm_interactions(experiment_id: str, limit: int = 50):
    """Retorna todas as interações com LLM-service"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        interactions = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entry = json.loads(entry_data)
                if entry.get('data_type') in ['llm_request', 'prompt']:
                    interactions.append(entry)
                    if len(interactions) >= limit:
                        break
        
        return {
            "experiment_id": experiment_id,
            "total_interactions": len(interactions),
            "interactions": interactions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/kubernetes-commands")
async def get_kubernetes_commands(experiment_id: str, limit: int = 50):
    """Retorna todos os comandos Kubernetes executados"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        commands = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entry = json.loads(entry_data)
                if entry.get('data_type') in ['kubernetes_command', 'kubernetes_result']:
                    commands.append(entry)
                    if len(commands) >= limit:
                        break
        
        return {
            "experiment_id": experiment_id,
            "total_commands": len(commands),
            "commands": commands
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/export")
async def export_experiment_data(experiment_id: str):
    """Exporta todos os dados do experimento"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        all_entries = []
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                all_entries.append(json.loads(entry_data))
        
        export_data = {
            "experiment_id": experiment_id,
            "export_timestamp": datetime.now().isoformat(),
            "total_entries": len(all_entries),
            "data_entries": all_entries
        }
        
        return export_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-collection/{experiment_id}/aggregated-metrics")
async def get_aggregated_metrics(experiment_id: str):
    """Retorna métricas agregadas extraídas dos dados coletados"""
    try:
        experiment_list_key = f'knowledge:experiment:{experiment_id}:entries'
        entry_ids = redis_client.lrange(experiment_list_key, 0, -1)
        
        # Extrair métricas reais dos dados coletados
        aggregated_metrics = {
            "experiment_id": experiment_id,
            "export_timestamp": datetime.now().isoformat(),
            "real_metrics": {
                "error_rate": None,
                "throughput": None,
                "network_latency": None,
                "cpu_usage_percent": None,
                "memory_usage_percent": None,
                "kube_znn_response_time_ms": None
            },
            "metrics_sources": []
        }
        
        for entry_id in entry_ids:
            key = f'knowledge:data_collection:{entry_id}'
            entry_data = redis_client.get(key)
            if entry_data:
                entry = json.loads(entry_data)
                
                # Extrair métricas de diferentes tipos de entrada
                if entry.get('data_type') == 'llm_request':
                    data = entry.get('data', {})
                    request_data = data.get('request', {})
                    context = request_data.get('context', {})
                    
                    # Extrair métricas do contexto do LLM
                    if context:
                        for metric in ['error_rate', 'throughput', 'network_latency', 'cpu_usage_percent', 'memory_usage_percent', 'kube_znn_response_time_ms']:
                            if metric in context and aggregated_metrics["real_metrics"][metric] is None:
                                aggregated_metrics["real_metrics"][metric] = context[metric]
                                aggregated_metrics["metrics_sources"].append({
                                    "metric": metric,
                                    "value": context[metric],
                                    "source": "llm_request_context",
                                    "entry_id": entry_id,
                                    "timestamp": entry.get('timestamp')
                                })
                
                elif entry.get('data_type') == 'template':
                    data = entry.get('data', {})
                    variables = data.get('variables', {})
                    
                    # Extrair métricas das variáveis do template
                    if variables:
                        for metric in ['error_rate', 'throughput', 'network_latency', 'used_system_cpu', 'used_system_memory', 'median_response_time']:
                            if metric in variables and aggregated_metrics["real_metrics"].get(metric.replace('used_system_', '').replace('median_', 'kube_znn_'), None) is None:
                                mapped_metric = metric.replace('used_system_', '').replace('median_', 'kube_znn_')
                                if mapped_metric in aggregated_metrics["real_metrics"]:
                                    aggregated_metrics["real_metrics"][mapped_metric] = variables[metric]
                                    aggregated_metrics["metrics_sources"].append({
                                        "metric": mapped_metric,
                                        "value": variables[metric],
                                        "source": "template_variables",
                                        "entry_id": entry_id,
                                        "timestamp": entry.get('timestamp')
                                    })
                
                elif entry.get('data_type') == 'monitor_data':
                    # Extrair métricas diretamente dos dados do monitor
                    for metric in ['error_rate', 'throughput', 'network_latency', 'cpu_usage_percent', 'memory_usage_percent', 'kube_znn_response_time_ms']:
                        if metric in entry and aggregated_metrics["real_metrics"][metric] is None:
                            aggregated_metrics["real_metrics"][metric] = entry[metric]
                            aggregated_metrics["metrics_sources"].append({
                                "metric": metric,
                                "value": entry[metric],
                                "source": "monitor_data",
                                "entry_id": entry_id,
                                "timestamp": entry.get('timestamp')
                            })
        
        return aggregated_metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para obter todo o conhecimento de um experimento
@app.get("/experiment/{experiment_id}")
async def get_experiment_knowledge(experiment_id: int):
    """Retorna todo conhecimento de um experimento específico"""
    try:
        knowledge = {
            'experiment_id': experiment_id,
            'servers': [],
            'monitor_data': {},
            'selected_prompts': {},
            'priority_criteria': {},
            'test_cases': [],
            'test_report': {}
        }
        
        # Buscar dados relacionados ao experimento
        server_data = redis_client.get('knowledge:servers:all')
        if server_data:
            knowledge['servers'] = json.loads(server_data)
        
        monitor_data = redis_client.get('knowledge:monitor:current')
        if monitor_data:
            knowledge['monitor_data'] = json.loads(monitor_data)
        
        prompts_data = redis_client.get('knowledge:selected_prompts:current')
        if prompts_data:
            knowledge['selected_prompts'] = json.loads(prompts_data)
        
        priority_data = redis_client.get('knowledge:priority:current')
        if priority_data:
            knowledge['priority_criteria'] = json.loads(priority_data)
        
        test_cases_data = redis_client.get('knowledge:test_cases:current')
        if test_cases_data:
            knowledge['test_cases'] = json.loads(test_cases_data)
        
        report_data = redis_client.get('knowledge:test_report:current')
        if report_data:
            knowledge['test_report'] = json.loads(report_data)
        
        return knowledge
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Legacy endpoint para compatibilidade
@app.post("/store-knowledge")
async def store_knowledge_legacy():
    """Armazena conhecimento/resultados (compatibilidade)"""
    try:
        results_data = redis_client.rpop('executor_to_knowledge')
        if not results_data:
            raise HTTPException(status_code=404, detail="No results available")
        
        results = json.loads(results_data)
        
        # Armazenar como relatório de teste
        await store_test_report(results)
        
        return {"status": "stored", "data": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/store-new-test-types")
async def store_new_test_types(data: dict):
    """Armazena novos tipos de teste detectados pelo Planner"""
    try:
        experiment_id = data.get('experiment_id', 'unknown')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        new_test_types = data.get('new_test_types', [])
        
        if not new_test_types:
            return {"message": "Nenhum novo tipo de teste para armazenar", "success": True}
        
        # Criar chave única para este armazenamento
        storage_key = f'knowledge:new_test_types:{experiment_id}:{timestamp}'
        
        # Armazenar dados completos
        redis_client.setex(storage_key, 86400 * 30, json.dumps(data))  # 30 dias
        
        # Adicionar à lista de novos tipos por experimento
        experiment_new_types_key = f'knowledge:experiment:{experiment_id}:new_test_types'
        redis_client.lpush(experiment_new_types_key, timestamp)
        redis_client.expire(experiment_new_types_key, 86400 * 30)
        
        # Adicionar à lista global de novos tipos
        global_new_types_key = 'knowledge:global:new_test_types'
        redis_client.lpush(global_new_types_key, timestamp)
        redis_client.expire(global_new_types_key, 86400 * 30)
        
        # Armazenar cada novo tipo individualmente para fácil consulta
        for test_type in new_test_types:
            type_key = f'knowledge:test_type:{test_type}:instances'
            redis_client.lpush(type_key, timestamp)
            redis_client.expire(type_key, 86400 * 30)
        
        logger.info(f"Novos tipos de teste armazenados: {new_test_types} para experimento {experiment_id}")
        
        return {
            "message": f"Novos tipos de teste armazenados com sucesso: {new_test_types}",
            "success": True,
            "experiment_id": experiment_id,
            "new_types": new_test_types,
            "timestamp": timestamp
        }
        
    except Exception as e:
        logger.error(f"Erro ao armazenar novos tipos de teste: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/new-test-types/{experiment_id}")
async def get_new_test_types(experiment_id: str, limit: int = 10):
    """Retorna novos tipos de teste detectados para um experimento"""
    try:
        experiment_new_types_key = f'knowledge:experiment:{experiment_id}:new_test_types'
        timestamps = redis_client.lrange(experiment_new_types_key, 0, limit - 1)
        
        new_types_data = []
        for timestamp in timestamps:
            storage_key = f'knowledge:new_test_types:{experiment_id}:{timestamp}'
            data = redis_client.get(storage_key)
            if data:
                new_types_data.append(json.loads(data))
        
        return {
            "experiment_id": experiment_id,
            "total_new_types": len(new_types_data),
            "new_types_data": new_types_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge")
async def get_knowledge():
    """Retorna conhecimento armazenado (compatibilidade)"""
    try:
        reports = redis_client.lrange('knowledge:test_report:history', 0, 9)
        knowledge_list = [json.loads(r) for r in reports]
        return {"knowledge": knowledge_list, "count": len(knowledge_list)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
