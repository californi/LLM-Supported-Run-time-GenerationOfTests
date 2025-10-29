# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import json
from datetime import datetime
from typing import Dict, Any, List
import os
import time
import logging
from huggingface_hub import InferenceClient, login

app = FastAPI(title="LLM Service", version="1.0.0")

# Configuração Redis
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# Configuração Hugging Face API
HF_API_TOKEN = os.getenv('HF_API_TOKEN', 'YOUR_HF_TOKEN_HERE')

# Controle de execução da API (para economizar créditos)
ENABLE_MISTRAL_API = os.getenv('ENABLE_MISTRAL_API', 'false').lower() == 'true'

# Fazer login e inicializar cliente
try:
    login(token=HF_API_TOKEN)
    print("Successfully logged in to Hugging Face")
    
    # Usar o modelo Mistral que funcionou antes
    hf_client = InferenceClient(model="mistralai/Mixtral-8x7B-Instruct-v0.1")
    print("Successfully initialized Hugging Face client with Mistral")
except Exception as e:
    print(f"Error initializing Hugging Face client: {e}")
    print("Using fallback responses for testing")
    hf_client = None

prompts_history = []

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMLogger:
    """Logger para LLM Service - persiste prompts e respostas"""
    
    def __init__(self):
        self.log_dir = "/app/logs/llm-service"
        os.makedirs(self.log_dir, exist_ok=True)
    
    def log_prompt_response(self, prompt_request: Dict[str, Any], response: str, 
                          prompt_type: str, experiment_id: str = "unknown", 
                          run_id: str = "unknown"):
        """Log completo do prompt e resposta"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"llm_prompt_response_{experiment_id}_{run_id}_{timestamp}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "experiment_id": experiment_id,
                "run_id": run_id,
                "prompt_type": prompt_type,
                "prompt_request": prompt_request,
                "prompt_text": prompt_request.get("prompt", ""),
                "response": response,
                "response_length": len(response),
                "model_used": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "service": "llm-service"
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"LLM prompt/response log saved: {filepath}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar log do LLM: {e}")

# Instanciar logger
llm_logger = LLMLogger()

class PromptRequest(BaseModel):
    context: Dict[str, Any]
    prompt_type: str = "test_generation"
    category: str = ""
    prompt: str = ""

class PromptResponse(BaseModel):
    timestamp: str
    context: Dict[str, Any]
    prompt: str
    response: str
    prompt_type: str

def call_huggingface_api(prompt: str, max_retries: int = 3) -> str:
    """Gera conteúdo usando a API Hugging Face com InferenceClient"""
    
    # Verificar se a API está habilitada
    if not ENABLE_MISTRAL_API:
        logger.warning("Mistral API está desabilitada. Retornando resposta simulada.")
        return """{
  "analysis_summary": {
    "recommended_test_type": "reachability",
    "justification": "API desabilitada - modo de economia de créditos",
    "priority": "low"
  }
}"""
    
    if hf_client is None:
        logger.warning("Hugging Face client not initialized. Using fallback response.")
        return """{
  "analysis_summary": {
    "recommended_test_type": "response_time",
    "justification": "Fallback response - client not initialized",
    "priority": "medium"
  }
}"""
    
    for attempt in range(max_retries):
        try:
            # Usar chat_completion como funcionou no teste
            response = hf_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating text: {str(e)}")
            if attempt == max_retries - 1:
                return f"Error: {str(e)}"
            time.sleep(2 ** attempt)  # Exponential backoff
    
    return "Error: Max retries exceeded"

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "llm-service", "timestamp": datetime.now().isoformat()}

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint"""
    try:
        # Verificar conectividade com Redis
        redis_client.ping()
        
        # Verificar se o cliente Hugging Face está inicializado
        hf_status = "connected" if hf_client is not None else "disconnected"
        
        return {
            "status": "ready", 
            "service": "llm-service",
            "dependencies": {
                "redis": "connected",
                "huggingface": hf_status,
                "mistral_api_enabled": ENABLE_MISTRAL_API
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "not_ready",
            "service": "llm-service", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/test-hf-api")
async def test_hf_api():
    """Testa a conectividade com a API Hugging Face"""
    try:
        test_prompt = "Generate a simple Python function that returns 'Hello World'"
        response = call_huggingface_api(test_prompt)
        
        return {
            "status": "success",
            "hf_api_response": response[:200] + "..." if len(response) > 200 else response,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/status")
async def get_status():
    """Retorna o status do serviço e configurações"""
    return {
        "status": "running",
        "mistral_api_enabled": ENABLE_MISTRAL_API,
        "hf_client_initialized": hf_client is not None,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/toggle-mistral-api")
async def toggle_mistral_api(enabled: bool):
    """Habilita/desabilita a API do Mistral para economizar créditos"""
    global ENABLE_MISTRAL_API
    ENABLE_MISTRAL_API = enabled
    
    logger.info(f"Mistral API {'habilitada' if enabled else 'desabilitada'}")
    
    return {
        "status": "success",
        "mistral_api_enabled": ENABLE_MISTRAL_API,
        "message": f"Mistral API {'habilitada' if enabled else 'desabilitada'}",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/select-prompts")
async def select_prompts(request: PromptRequest):
    """Seleciona prompts da categoria baseado no contexto"""
    global prompts_history
    
    try:
        context = request.context
        category = request.category
        health_criterion = context.get('health_criterion', 'Unknown')
        
        # Buscar prompts da categoria do Knowledge
        selected_prompts = select_category_prompts(category, health_criterion, context)
        
        prompt_response = {
            'timestamp': datetime.now().isoformat(),
            'context': context,
            'category': category,
            'selected_prompts': selected_prompts,
            'health_criterion': health_criterion,
            'prompt_type': 'prompt_selection'
        }
        
        prompts_history.append(prompt_response)
        redis_client.lpush('llm:prompts', json.dumps(prompt_response))
        
        return prompt_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-test-cases")
async def generate_test_cases(request: PromptRequest):
    """Gera casos de teste usando LLM baseado nos prompts selecionados"""
    global prompts_history
    
    try:
        context = request.context
        prompts = context.get('prompts', [])
        health_criterion = context.get('health_criterion', 'Unknown')
        experiment_id = context.get('experiment_id', 1)
        
        # Gerar casos de teste baseado nos prompts
        test_cases = generate_test_cases_from_prompts(prompts, health_criterion, experiment_id, context)
        
        generation_response = {
            'timestamp': datetime.now().isoformat(),
            'context': context,
            'generated_test_cases': test_cases,
            'health_criterion': health_criterion,
            'experiment_id': experiment_id,
            'prompt_type': 'test_generation'
        }
        
        prompts_history.append(generation_response)
        redis_client.lpush('llm:generations', json.dumps(generation_response))
        
        return generation_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def select_category_prompts(category: str, health_criterion: str, context: Dict[str, Any]) -> List[str]:
    """Seleciona prompts apropriados da categoria usando LLM"""
    
    # Criar prompt para o LLM gerar prompts específicos
    llm_prompt = f"""Generate 3 specific test prompts for Kubernetes microservice testing.

Category: {category}
Health Criterion: {health_criterion}
Experiment ID: {context.get('experiment_id', 1)}

Generate 3 test prompts that are:
1. Specific to the {category} category
2. Appropriate for {health_criterion} health criterion
3. Focused on Kubernetes microservice testing
4. Include specific kubectl commands or HTTP requests

Return only the 3 prompts, one per line, in Portuguese."""
    
    # Chamar LLM para gerar prompts
    llm_response = call_huggingface_api(llm_prompt)
    
    # COMENTADO: Fallback para prompts hardcoded se LLM falhar
    # Sempre usar LLM Mistral - sem fallbacks
    # if "Error:" in llm_response or not llm_response.strip():
    #     category_prompts = {
    #         'reachability': [
    #             'Verifique se todos os pods kube-znn estão acessíveis via HTTP',
    #             'Teste a conectividade de cada pod individualmente',
    #             'Valide se o serviço kube-znn responde em todas as rotas'
    #         ],
    #         'response_time': [
    #             'Meça o tempo de resposta das requisições ao kube-znn',
    #             'Valide se o tempo de resposta está dentro dos SLAs',
    #             'Verifique latência sob diferentes cargas'
    #         ],
    #         'load': [
    #             'Teste o comportamento do sistema sob alta demanda',
    #             'Avalie o limite de capacidade do kube-znn',
    #             'Valide escalabilidade e degradação graceful'
    #         ]
    #     }
    #     return category_prompts.get(category, category_prompts['response_time'])
    
    # Processar resposta do LLM
    prompts = [line.strip() for line in llm_response.strip().split('\n') if line.strip()]
    return prompts[:3] if prompts else ["LLM Mistral deve sempre gerar prompts válidos"]

def generate_test_cases_from_prompts(
    prompts: List[str], 
    health_criterion: str, 
    experiment_id: int,
    context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Gera casos de teste baseado nos prompts usando LLM"""
    test_cases = []
    
    # Criar prompt para o LLM gerar casos de teste completos
    llm_prompt = f"""Generate a test case for Kubernetes microservice testing in JSON format.

Context: Health Criterion: {health_criterion}, Experiment ID: {experiment_id}

Test Prompt: {prompts[0] if prompts else 'Test Kubernetes service'}

Generate JSON with fields: test_id, name, type, description, criterion, expected, command, oracle"""
    
    # Chamar LLM para gerar casos de teste
    llm_response = call_huggingface_api(llm_prompt)
    
    # Tentar parsear JSON da resposta do LLM
    try:
        if llm_response and not llm_response.startswith("Error:"):
            # Limpar resposta e tentar extrair JSON
            cleaned_response = llm_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response.replace('```json', '').replace('```', '').strip()
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response.replace('```', '').strip()
            
            parsed = json.loads(cleaned_response)
            if isinstance(parsed, dict):
                # Se for um único objeto, colocar em uma lista
                return [parsed]
            elif isinstance(parsed, list) and len(parsed) > 0:
                return parsed
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"LLM response: {llm_response}")
    
    # COMENTADO: Fallback para geração hardcoded se LLM falhar
    # Sempre usar LLM Mistral - sem fallbacks
    # Se o LLM não retornou JSON válido, retornar erro
    if not test_cases:
        raise Exception("LLM Mistral deve sempre gerar casos de teste válidos em formato JSON")
    
    return test_cases

def generate_command_from_prompt(prompt: str, context: Dict[str, Any]) -> str:
    """Gera comando de teste baseado no prompt usando LLM Mistral"""
    
    # Criar prompt para o LLM gerar comando kubectl apropriado
    llm_prompt = f"""Generate a kubectl command for Kubernetes testing based on the following prompt and system context.

PROMPT: {prompt}

SYSTEM CONTEXT:
{context}

Generate a single kubectl command that tests the described functionality considering the current system state.
The command should be specific, executable, and appropriate for testing the kube-znn service.

Consider the current metrics, load conditions, and infrastructure status when generating the command.

Return only the command, no explanations or additional text.

Example format: kubectl get pods -n default -l app=kube-znn"""
    
    # Chamar LLM para gerar comando
    llm_response = call_huggingface_api(llm_prompt)
    
    # Limpar resposta e retornar comando
    if llm_response and not llm_response.startswith("Error:"):
        # Extrair apenas o comando (primeira linha)
        command = llm_response.strip().split('\n')[0].strip()
        # Remover markdown se presente
        command = command.replace('```bash', '').replace('```', '').strip()
        return command
    else:
        # COMENTADO: Fallback hardcoded removido - sempre usar LLM Mistral
        raise Exception("LLM Mistral deve sempre gerar comandos válidos")

def generate_oracle_from_prompt(prompt: str, health_criterion: str) -> str:
    """Gera oráculo de teste baseado no prompt e critério usando LLM Mistral"""
    
    # Criar prompt para o LLM gerar oráculo apropriado
    llm_prompt = f"""Generate a test oracle (validation criteria) for Kubernetes testing based on the following prompt and health criterion.

PROMPT: {prompt}
HEALTH CRITERION: {health_criterion}

Generate a specific oracle that validates the test results considering the current system state.
The oracle should be clear, measurable, and appropriate for the test type.

Consider the health criterion and current system conditions when generating the oracle.

Return only the oracle validation criteria, no explanations or additional text.

Example format: Pod status should be 'Running' and readiness probe should be 'Success'"""
    
    # Chamar LLM para gerar oráculo
    llm_response = call_huggingface_api(llm_prompt)
    
    # Limpar resposta e retornar oráculo
    if llm_response and not llm_response.startswith("Error:"):
        # Extrair apenas o oráculo (primeira linha)
        oracle = llm_response.strip().split('\n')[0].strip()
        # Remover markdown se presente
        oracle = oracle.replace('```', '').strip()
        return oracle
    else:
        # COMENTADO: Fallback hardcoded removido - sempre usar LLM Mistral
        raise Exception("LLM Mistral deve sempre gerar oráculos válidos")

@app.post("/generate-prompt")
async def generate_prompt(request: PromptRequest):
    """Gera prompts para casos de teste (legacy) - CORRIGIDO para evitar cache"""
    global prompts_history
    
    try:
        context = request.context
        prompt_type = request.prompt_type
        experiment_id = context.get('experiment_id', 'unknown')
        run_id = context.get('run_id', 'unknown')
        
        # CORREÇÃO: Adicionar timestamp único para evitar cache
        unique_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # Use the prompt from the request if provided, otherwise generate one
        if hasattr(request, 'prompt') and request.prompt:
            prompt = request.prompt
            
            # CORREÇÃO: Adicionar experiment_id e timestamp ao prompt para garantir unicidade
            enhanced_prompt = f"""
EXPERIMENT_ID: {experiment_id}
RUN_ID: {run_id}
TIMESTAMP: {unique_timestamp}
UNIQUE_SESSION: {experiment_id}_{run_id}_{unique_timestamp}

{prompt}

IMPORTANTE: Esta é uma requisição única para o experimento {experiment_id}, run {run_id}. 
NÃO reutilize dados de experimentos anteriores. Gere uma resposta específica para este momento.
"""
            
            # Call LLM with the enhanced prompt
            response = call_huggingface_api(enhanced_prompt)
        else:
            # Sempre usar prompt fornecido - LLM Mistral deve sempre receber prompt válido
            raise HTTPException(status_code=400, detail="Prompt é obrigatório - LLM Mistral deve sempre receber prompt válido")
        
        prompt_response = {
            'timestamp': datetime.now().isoformat(),
            'unique_session_id': f"{experiment_id}_{run_id}_{unique_timestamp}",
            'context': context,
            'prompt': prompt,
            'enhanced_prompt': enhanced_prompt if 'enhanced_prompt' in locals() else prompt,
            'response': response,
            'prompt_type': prompt_type,
            'experiment_id': experiment_id,
            'run_id': run_id
        }
        
        # Log completo do prompt e resposta
        llm_logger.log_prompt_response(request.dict(), response, prompt_type, experiment_id, run_id)
        
        prompts_history.append(prompt_response)
        redis_client.lpush('llm:prompts', json.dumps(prompt_response))
        
        return prompt_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prompts")
async def get_prompts():
    """Retorna histórico de prompts"""
    try:
        prompts = redis_client.lrange('llm:prompts', 0, 9)
        prompt_list = [json.loads(p) for p in prompts]
        return {"prompts": prompt_list, "count": len(prompt_list)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prompts/{prompt_type}")
async def get_prompts_by_type(prompt_type: str):
    """Retorna prompts de um tipo específico"""
    try:
        prompts = redis_client.lrange('llm:prompts', 0, -1)
        filtered_prompts = []
        
        for prompt_data in prompts:
            prompt = json.loads(prompt_data)
            if prompt.get('prompt_type') == prompt_type:
                filtered_prompts.append(prompt)
        
        return {"prompt_type": prompt_type, "prompts": filtered_prompts, "count": len(filtered_prompts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs():
    """Retorna logs do LLM Service"""
    try:
        # Retornar logs dos arquivos salvos
        logs_dir = "/app/logs/llm-service"
        log_files = []
        
        if os.path.exists(logs_dir):
            for filename in os.listdir(logs_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(logs_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            log_data = json.load(f)
                            log_files.append({
                                "filename": filename,
                                "data": log_data
                            })
                    except Exception as e:
                        log_files.append({
                            "filename": filename,
                            "error": str(e)
                        })
        
        return {"logs": log_files, "count": len(log_files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)