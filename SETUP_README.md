# Complete Experiment Setup

## What's Included

This folder contains a complete, ready-to-use experimental setup for the microservices system.

### Structure
```
LLM-Supported-Runtime-GenerationOfTests/
├── README.md                          # Main documentation
├── TRANSLATION_SUMMARY.md             # Translation details
├── SETUP_README.md                    # This file
│
├── microservices/                     # All microservices
│   ├── planner/                       # Test planning service
│   ├── executor/                      # Test execution service
│   ├── analyzer/                      # System analysis service
│   ├── knowledge/                     # Knowledge base service
│   ├── load-generator/                # Load generation service
│   └── monitor/                       # System monitoring service
│
├── k8s/                               # Kubernetes configurations
│   ├── microservices-v18.yaml        # Main deployment
│   ├── kube-znn-hpa.yaml             # Auto-scaling config
│   ├── load-generator.yaml           # Load generator config
│   └── [other k8s configs]
│
├── experiments/                       # 6 Final experiment results
│   ├── 600k_load_*/                   # Load test with 600k model
│   ├── 600k_reachability_*/           # Reachability test 600k
│   ├── 600k_response_time_*/          # Response time test 600k
│   ├── 800k_load_*/                   # Load test with 800k model
│   ├── 800k_reachability_*/           # Reachability test 800k
│   └── 800k_response_time_*/          # Response time test 800k
│
├── execute_complete_experiment.py    # Main experiment script
└── cenarios_*.json                    # Scenario configurations
```

## Quick Start

### 1. Prerequisites
- Python 3.8+
- Docker
- Kubernetes cluster (or Minikube/Kind)
- kubectl configured

### 2. Setup Environment
```bash
cd experimento_completo

# Create your environment file (YOU NEED TO ADD YOUR VALUES)
cat > config.env <<EOF
KNOWLEDGE_URL=http://knowledge:8000
LLM_SERVICE_URL=http://llm-service:8000
EXPERIMENT_ID=E1-1-1
TARGET_SYSTEM_QUALITY=600
TARGET_SYSTEM_REPLICAS=3
EOF

# Install dependencies
pip install -r microservices/*/requirements.txt
```

### 3. Deploy to Kubernetes
```bash
# Apply all deployments
kubectl apply -f k8s/

# Wait for pods to be ready
kubectl get pods -w

# Check service health
kubectl get svc
```

### 4. Run Experiments
```bash
# Run the complete experiment
python execute_complete_experiment.py

# Results will be saved in: experiment_outputs/
```

## Experiment Types

The 6 experiments included:
1. **Load Testing** - Tests system capacity under load
2. **Reachability Testing** - Tests service connectivity
3. **Response Time Testing** - Tests system performance

Each with two model sizes:
- **600k** - Smaller model for baseline testing
- **800k** - Larger model for stress testing

## Important Notes

### ⚠️ Security
- **NO sensitive data included** (tokens, passwords, API keys)
- **NO environment configurations** included
- You **MUST** set up your own:
  - API credentials
  - Database connections
  - External service URLs

### ✅ Translations
All code has been translated to English:
- Comments and docstrings
- Log messages
- User-facing strings
- Error messages

### 📋 What to Configure

1. **Environment Variables** - Create `config.env` with your values
2. **API Tokens** - Add your LLM service tokens
3. **Database Credentials** - Configure Redis/other databases
4. **External URLs** - Update service URLs in k8s configs

## Directory Size
Total: ~2.4MB

## Support

For issues or questions about the experiments:
1. Check `README.md` for documentation
2. Review `TRANSLATION_SUMMARY.md` for translation details
3. Check experiment results in `experiments/` folder

## Next Steps

After running experiments:
1. Review results in `experiment_outputs/`
2. Compare 600k vs 800k performance
3. Analyze JSON files for detailed metrics
4. Use the experiment results for your research/paper

