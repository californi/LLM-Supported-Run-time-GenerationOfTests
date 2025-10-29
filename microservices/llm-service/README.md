# LLM Service - Integração com Hugging Face API

## Mudanças Implementadas

O serviço `llm-service` foi modificado para fazer chamadas reais à API Hugging Face em vez de usar dados hardcoded.

### Principais Modificações

1. **Integração com Hugging Face API**
   - Adicionada função `call_huggingface_api()` para fazer chamadas à API
   - Configuração do token de autenticação via variável de ambiente
   - Uso do modelo `bigcode/starcoder2-15b` otimizado para geração de código Python

2. **Geração Inteligente de Prompts**
   - A função `select_category_prompts()` agora usa LLM para gerar prompts específicos
   - Prompts são gerados baseados no contexto do experimento (CPU, memória, pods, etc.)
   - Fallback para prompts hardcoded em caso de falha da API

3. **Geração Inteligente de Casos de Teste**
   - A função `generate_test_cases_from_prompts()` agora usa LLM para gerar casos de teste completos
   - Casos de teste são gerados em formato JSON estruturado
   - Fallback para geração hardcoded em caso de falha da API

4. **Novo Endpoint de Teste**
   - Adicionado endpoint `/test-hf-api` para testar conectividade com a API Hugging Face

### Configuração

#### Variáveis de Ambiente
- `HF_API_TOKEN`: Token de autenticação da Hugging Face (padrão: YOUR_HF_TOKEN_HERE)
- `REDIS_HOST`: Host do Redis (padrão: redis)
- `REDIS_PORT`: Porta do Redis (padrão: 6379)

#### Dependências
- `fastapi`: Framework web
- `uvicorn`: Servidor ASGI
- `redis`: Cliente Redis
- `requests`: Cliente HTTP para chamadas à API
- `pydantic`: Validação de dados

### Uso

#### Testar Conectividade
```bash
curl http://localhost:8000/test-hf-api
```

#### Gerar Prompts
```bash
curl -X POST http://localhost:8000/select-prompts \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "health_criterion": "Saudavel",
      "experiment_id": 1,
      "cpu_allocated": 100,
      "memory_allocated": 256,
      "pods": 3
    },
    "category": "response_time"
  }'
```

#### Gerar Casos de Teste
```bash
curl -X POST http://localhost:8000/generate-test-cases \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "health_criterion": "Saudavel",
      "experiment_id": 1,
      "prompts": [
        "Meça o tempo de resposta das requisições ao kube-znn",
        "Valide se o tempo de resposta está dentro dos SLAs"
      ]
    }
  }'
```

### Características Técnicas

- **Retry Logic**: Sistema de retry com backoff exponencial para lidar com carregamento do modelo
- **Timeout**: Timeout de 30 segundos para chamadas à API
- **Error Handling**: Tratamento robusto de erros com fallback para métodos hardcoded
- **JSON Parsing**: Limpeza e parsing inteligente de respostas JSON do LLM
- **Logging**: Logs detalhados para debugging

### Modelo Utilizado

- **Modelo**: `bigcode/starcoder2-15b`
- **Especialização**: Geração de código Python, casos de teste e análise de software
- **Parâmetros**:
  - `max_new_tokens`: 512
  - `temperature`: 0.7
  - `top_p`: 0.9
  - `do_sample`: True

### Benefícios

1. **Flexibilidade**: Prompts e casos de teste são gerados dinamicamente baseados no contexto
2. **Qualidade**: Uso de modelo especializado em código Python e testes
3. **Robustez**: Sistema de fallback garante funcionamento mesmo com falhas da API
4. **Escalabilidade**: Fácil troca de modelo ou provedor de API
5. **Manutenibilidade**: Código limpo e bem documentado
