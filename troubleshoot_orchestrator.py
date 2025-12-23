"""
Main troubleshooting orchestrator
Coordinates log collection, deterministic checks, and AI analysis
"""

import subprocess
import sys
import os
import time
from pathlib import Path

from troubleshoot.collector import LogCollector
from troubleshoot.checks import SystemChecker
from troubleshoot.report import ReportGenerator
from ai.interface import LLMInterface

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class TroubleshootOrchestrator:
    def __init__(self):
        self.collector = LogCollector()
        self.checker = SystemChecker()
        self.reporter = ReportGenerator()
        self.llm = None
    
    def run_diagnostic(self, vm_name=None, failed_step=None):
        """Run full diagnostic without AI"""
        print(f"\n{BLUE}Running system diagnostics...{RESET}")
        
        # Collecting all diagnostic data
        print("Collecting system information...")
        diagnostic_data, log_file = self.collector.collect_all(vm_name, failed_step)
        
        print("Running deterministic checks...")
        check_results = self.checker.run_all_checks(diagnostic_data)
        
        self.reporter.print_diagnostic_summary(diagnostic_data, check_results)
        
        print(f"\n{GREEN}Full diagnostic saved to:{RESET} {log_file}")
        
        return diagnostic_data, check_results, log_file
    
    def setup_llm(self, use_container=True, model="llama3.1:8b"):
        """Set up LLM connection"""
        if use_container:
            try:
                result = subprocess.run(
                    ["docker", "ps", "--filter", "name=vfioh-ollama", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if "vfioh-ollama" not in result.stdout:
                    print(f"\n{YELLOW}Ollama container not running{RESET}")
                    print("Starting container...")
                    
                    # Try to start with docker-compose
                    compose_path = Path("llm_container/docker-compose.yml")
                    if compose_path.exists():
                        subprocess.run(
                            ["docker-compose", "-f", str(compose_path), "up", "-d"],
                            check=True
                        )
                        print(f"{GREEN}✅ Container started{RESET}")
                        print("Waiting for service to be ready...")
                        import time
                        time.sleep(5)
                    else:
                        print(f"{RED}❌ docker-compose.yml not found in llm_container/{RESET}")
                        print("Please run: cd llm_container && docker-compose up -d")
                        return False
            
            except subprocess.CalledProcessError as e:
                print(f"{RED}❌ Failed to start container: {e}{RESET}")
                return False
            except FileNotFoundError:
                print(f"{RED}❌ Docker not found. Please install Docker{RESET}")
                return False
        
        self.llm = LLMInterface(provider="ollama", model=model)
        
        if not self.llm.is_available():
            print(f"{RED}❌ Cannot connect to Ollama{RESET}")
            if use_container:
                print("The container may not be ready yet. Please wait and try again.")
            else:
                print("Make sure Ollama is running: ollama serve")
            return False
        
        print(f"{GREEN}✅ Connected to Ollama{RESET}")
        
        models = self.llm.list_models()
        if not models:
            print(f"{YELLOW}No models found{RESET}")
            print(f"Pulling model: {model}")
            success, message = self.llm.ensure_model(model)
            if not success:
                print(f"{RED}❌ {message}{RESET}")
                return False
        elif model not in models:
            print(f"{YELLOW}Model '{model}' not found{RESET}")
            print(f"Available models: {', '.join(models)}")
            print(f"Pulling {model}...")
            success, message = self.llm.ensure_model(model)
            if not success:
                print(f"{RED}❌ {message}{RESET}")
                return False
        else:
            print(f"{GREEN}✅ Model '{model}' ready{RESET}")
        
        return True
    
    def run_ai_analysis(self, diagnostic_data, check_results):
        """Run AI analysis on diagnostic data"""
        if not self.llm:
            print(f"{RED}❌ LLM not initialized{RESET}")
            return None
        
        print(f"\n{BLUE}Running AI analysis...{RESET}")
        print("This may take 30-60 seconds...")
        
        formatted_data = self.reporter.format_for_llm(diagnostic_data, check_results)
        llm_response, error = self.llm.analyze_diagnostics(formatted_data)
        
        if error:
            print(f"{RED}❌ AI analysis failed: {error}{RESET}")
            return None
        
        self.reporter.print_llm_analysis(llm_response)
        
        return llm_response
    
    def execute_recommendation(self, command):
        """Execute a recommended command with user confirmation"""
        print(f"\n{YELLOW}Command to execute:{RESET}")
        print(f"  {command}")
        
        confirm = input(f"\n{BLUE}Execute this command? (yes/no):{RESET} ").strip().lower()
        
        if confirm not in ['yes', 'y']:
            print("Skipped")
            return False, "User declined"
        
        print(f"\n{GREEN}Executing...{RESET}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"{GREEN}✅ Command succeeded{RESET}")
                if result.stdout:
                    print("Output:")
                    print(result.stdout)
                return True, result.stdout
            else:
                print(f"{RED}❌ Command failed (exit code {result.returncode}){RESET}")
                if result.stderr:
                    print("Error output:")
                    print(result.stderr)
                return False, result.stderr
        
        except subprocess.TimeoutExpired:
            print(f"{RED}❌ Command timed out{RESET}")
            return False, "Timeout"
        except Exception as e:
            print(f"{RED}❌ Error executing command: {e}{RESET}")
            return False, str(e)
    
    def interactive_troubleshoot(self, vm_name=None, failed_step=None):
        """Interactive troubleshooting session"""
        # Collecting diagnostic data
        print(f"\n{BLUE}Collecting system diagnostic data...{RESET}")
        diagnostic_data, log_file = self.collector.collect_all(vm_name, failed_step)
        check_results = self.checker.run_all_checks(diagnostic_data)
        
        print(f"{GREEN}✓ Diagnostic data collected{RESET}")
        print(f"Full diagnostic saved to: {log_file}\n")
        
        from main import show_menu
        
        llm_options = [
            ("Containerized Ollama (recommended)", "container"),
            ("Existing Ollama installation", "local"),
            ("Back to Main Menu", "back")
        ]
        
        llm_choice = show_menu(llm_options, title="Choose LLM Source")
        
        if llm_choice == "back":
            return
        
        use_container = llm_choice == "container"
        
        if use_container:
            model_options = [
                ("llama3.1:8b (Recommended - 8GB RAM)", "llama3.1:8b"),
                ("llama3.2:3b (Faster - 4GB RAM)", "llama3.2:3b"),
                ("mixtral:8x7b (Most accurate - 16GB RAM)", "mixtral:8x7b"),
                ("Enter custom model name", "custom"),
                ("Back", "back")
            ]
            
            model = show_menu(model_options, title="Choose Model")
            
            if model == "back":
                return self.interactive_troubleshoot(vm_name, failed_step)
            elif model == "custom":
                print("\033[2J\033[H", end="", flush=True)
                print(f"{BLUE}Enter Custom Model Name{RESET}")
                print("="*70)
                print("Examples: llama3:70b, codellama:13b, mistral:latest")
                print("="*70)
                model = input("\nModel name: ").strip()
                if not model:
                    print(f"{RED}No model specified, returning to menu{RESET}")
                    time.sleep(2)
                    return self.interactive_troubleshoot(vm_name, failed_step)
        else:
            print(f"\n{BLUE}Checking for local Ollama installation...{RESET}")
            
            try:
                result = subprocess.run(
                    ["ollama", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode != 0 or "could not connect" in result.stderr.lower():
                    print(f"{RED}❌ Ollama is not running{RESET}")
                    print("Please start Ollama first: ollama serve")
                    input("\nPress Enter to return to menu...")
                    return
                
                # Parsing Ollama output
                lines = result.stdout.strip().split('\n')
                if len(lines) <= 1:
                    print(f"{YELLOW}No models found in local Ollama{RESET}")
                    print("Please pull a model first: ollama pull llama3.1:8b")
                    input("\nPress Enter to return to menu...")
                    return
                
                # Grabbing model names
                available_models = []
                for line in lines[1:]:  # Skipping header
                    parts = line.split()
                    if parts:
                        model_name = parts[0]
                        available_models.append(model_name)
                
                if not available_models:
                    print(f"{YELLOW}No models found in local Ollama{RESET}")
                    print("Please pull a model first: ollama pull llama3.1:8b")
                    input("\nPress Enter to return to menu...")
                    return
                
                model_options = [(f"{model}", model) for model in available_models]
                model_options.append(("Back", "back"))
                
                model = show_menu(model_options, title="Select Model from Local Ollama")
                
                if model == "back":
                    return self.interactive_troubleshoot(vm_name, failed_step)
                
            except FileNotFoundError:
                print(f"{RED}❌ Ollama command not found{RESET}")
                print("Please install Ollama: https://ollama.com")
                input("\nPress Enter to return to menu...")
                return
            except Exception as e:
                print(f"{RED}❌ Error checking Ollama: {e}{RESET}")
                input("\nPress Enter to return to menu...")
                return
        
        # Clears screen
        print("\033[2J\033[H", end="", flush=True)
        
        if not self.setup_llm(use_container, model):
            print(f"{RED}Failed to set up LLM{RESET}")
            return
        
        llm_response = self.run_ai_analysis(diagnostic_data, check_results)
        
        if not llm_response:
            return
        
        recommendations = llm_response.get("recommendations", [])
        
        if not recommendations:
            print(f"\n{YELLOW}No specific recommendations from AI{RESET}")
            return
        
        print(f"\n{BLUE}Process recommendations?{RESET}")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{GREEN}Recommendation {i}/{len(recommendations)}:{RESET}")
            print(f"  {rec['description']}")
            
            command = rec.get('command')
            if not command or command == "null":
                print(f"  {YELLOW}(Manual action required - no command){RESET}")
                input("Press Enter to continue...")
                continue
            
            success, output = self.execute_recommendation(command)
            
            if not success:
                print(f"\n{YELLOW}Command failed. Continue with next recommendation?{RESET}")
                cont = input("Continue? (yes/no): ").strip().lower()
                if cont not in ['yes', 'y']:
                    break
        
        print(f"\n{GREEN}Troubleshooting session complete{RESET}")
        print(f"Diagnostic log saved to: {log_file}")