# Complete Microservices Experiment Setup

This folder contains all necessary components to run the microservices experiments without sensitive information.

## Structure

```
LLM-Supported-Runtime-GenerationOfTests/
├── microservices/        # All microservices with Dockerfiles
│   ├── planner/
│   ├── executor/
│   ├── analyzer/
│   ├── knowledge/
│   ├── load-generator/
│   └── monitor/
├── k8s/                  # Kubernetes deployments and configs
├── experiments/          # 6 final experiment results
│   ├── 600k_load_20251027_095555/
│   ├── 600k_reachability_20251027_095142/
│   ├── 600k_response_time_20251027_095355/
│   ├── 800k_load_20251027_012149/
│   ├── 800k_reachability_20251027_095758/
│   └── 800k_response_time_20251027_001349_copiar/
├── cenarios_*.json       # User scenario configurations
└── execute_complete_experiment.py   # Main experiment execution script
```

## Components

### Microservices
All microservices have been translated to English (comments, docstrings, log messages).
Each service includes:
- `app.py` - Main application code
- `Dockerfile` - Container configuration
- `requirements.txt` - Python dependencies

### Kubernetes Configuration
- Deployments for each microservice
- ConfigMaps and Secrets (no sensitive data included)
- HPA (Horizontal Pod Autoscaler) configurations
- Network policies

### Experiment Script
- `execute_complete_experiment.py` - Main script to run experiments
- `cenarios_*.json` - User scenario definitions

### Final Experiments
The 6 experiments include:
- **600k_load** - Load testing with 600k users
- **600k_reachability** - Reachability testing with 600k users
- **600k_response_time** - Response time testing with 600k users
- **800k_load** - Load testing with 800k users
- **800k_reachability** - Reachability testing with 800k users
- **800k_response_time** - Response time testing with 800k users

## Important Notes

⚠️ **Sensitive Data Removed**
- No API tokens included
- No usernames or passwords included
- No environment variables with secrets included
- `config.env` and similar files have been excluded

## Usage

1. Set up your environment variables (create a `config.env` file with your values)
2. Deploy microservices to Kubernetes:
   ```bash
   kubectl apply -f k8s/
   ```
3. Run experiments:
   ```bash
   python execute_complete_experiment.py
   ```
