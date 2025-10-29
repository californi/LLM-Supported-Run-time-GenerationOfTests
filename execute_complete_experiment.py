#!/usr/bin/env python3
"""
Executes the complete experiment using experiment_monitor_simulator.py
Modifies input data to use 600k or 800k
"""

import json
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_model_scenarios(model_size: str):
    """Loads scenarios for a model"""
    filename = f"cenarios_{model_size}.json"
    with open(filename, 'r') as f:
        return json.load(f)

def create_scenario_data_for_experiment(model: str, scenario_key: str):
    """Creates scenario data in the format expected by experiment_monitor_simulator"""
    
    scenarios = load_model_scenarios(model)
    scenario = scenarios.get(scenario_key.upper())
    
    if not scenario:
        return None
    
    # Convert to experiment_monitor_simulator.py format
    return {
        "timestamp": "2025-10-26T16:00:00",
        "scenario": scenario_key.lower(),
        "description": scenario['description'],
        "metrics": {
            "cpu_usage": scenario['targets']['cpu_percent'],
            "memory_usage": scenario['targets']['memory_percent'],
            "response_time": scenario['targets']['response_time_ms'],
            "error_rate": scenario['targets']['error_rate'],
            "throughput": 0,
            "network_latency": 0,
            "active_pods": scenario['targets']['pods_active'],
            "failed_pods": scenario['targets'].get('pods_failing', 0),
            "pending_pods": scenario['targets'].get('pods_failing', 0),
            "concurrent_users": 0,
            "request_rate": 0,
            "session_duration": 0
        }
    }

def run_experiment_with_model(model: str):
    """Runs complete experiment for a model"""
    
    print(f"\n{'='*80}")
    print(f"🚀 RUNNING COMPLETE EXPERIMENT: {model}")
    print(f"{'='*80}\n")
    
    # Import MonitorSimulator from experiment_monitor_simulator.py
    sys.path.insert(0, '.')
    from experiment_monitor_simulator import MonitorSimulator
    
    simulator = MonitorSimulator()
    
    # Define custom functions to use 600k or 800k data
    original_generate = simulator.generate_scenario_data
    
    def generate_with_model(model_size):
        def generate(scenario_type):
            data = create_scenario_data_for_experiment(model_size, scenario_type)
            if data:
                return data
            return original_generate(scenario_type)
        return generate
    
    # Replace the generation function
    simulator.generate_scenario_data = lambda scenario_type: create_scenario_data_for_experiment(model, scenario_type)
    
    scenarios = ['reachability', 'response_time', 'load']
    
    for scenario in scenarios:
        try:
            print(f"\n📊 Running scenario: {scenario.upper()}")
            
            # Gerar dados
            scenario_data = simulator.generate_scenario_data(scenario)
            print(f"   Input: CPU {scenario_data['metrics']['cpu_usage']:.1f}%, "
                  f"Mem {scenario_data['metrics']['memory_usage']:.1f}%, "
                  f"Resp {scenario_data['metrics']['response_time']:.1f}ms")
            
            # Populate Knowledge
            if simulator.populate_knowledge(scenario_data):
                print(f"   ✅ Knowledge populated")
            else:
                print(f"   ⚠️ Problem populating Knowledge (service offline)")
            
            # Trigger Analyzer (only works if services are online)
            if simulator.check_service_health():
                analyzer_result = simulator.trigger_analyzer(scenario_data)
                if analyzer_result:
                    print(f"   ✅ Analyzer executed")
            
            # Collect and save results (even if services offline)
            final_results = simulator.collect_final_results()
            
            # Save results manually if necessary
            import os
            from datetime import datetime
            
            output_dir = f"experiment_outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            scenario_dir = f"{output_dir}/{model}_{scenario}_{timestamp}"
            os.makedirs(scenario_dir, exist_ok=True)
            
            # Salvar dados
            with open(f"{scenario_dir}/input_data.json", 'w') as f:
                json.dump(scenario_data, f, indent=2)
            
            with open(f"{scenario_dir}/results.json", 'w') as f:
                json.dump(final_results, f, indent=2)
            
            print(f"   💾 Results saved in: {scenario_dir}")
            
            import time
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error in {scenario}: {e}")
    
    print(f"\n✅ Experiment {model} completed!")
    print()

def main():
    """Runs experiments for 600k and 800k"""
    
    print("\n" + "="*80)
    print("🧪 COMPLETE APE-K FLOW EXECUTION")
    print("="*80)
    print("\nGenerating files in experiment_outputs/ for 600k vs 800k comparison\n")
    
    models = ['600k', '800k']
    
    for model in models:
        try:
            run_experiment_with_model(model)
        except Exception as e:
            logger.error(f"Error with model {model}: {e}")
    
    print("="*80)
    print("✅ EXPERIMENTS COMPLETED")
    print("="*80)
    print("\nFiles generated in: experiment_outputs/")
    print("\nTo compare:")
    print("  → ls -lht experiment_outputs/ | head -20")
    print("  → Compare the generated JSON files")
    print()

if __name__ == "__main__":
    main()








