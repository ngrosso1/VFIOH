"""
Main troubleshooting orchestrator
Coordinates log collection, deterministic checks, and AI analysis
"""

import subprocess
import sys
import os
from pathlib import Path

from troubleshoot.collector import LogCollector
from troubleshoot.checks import SystemChecker
from troubleshoot.report import ReportGenerator
from ai.interface import LLMInterface

# Colors
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
        
        # Collect all diagnostic data
        print("Collecting system information...")
        diagnostic_data, log_file = self.collector.collect_all(vm_name, failed_step)
        
        # Run deterministic checks
        print("Running deterministic checks...")
        check_results = self.checker.run_all_checks(diagnostic_data)
        
        # Print report
        self.reporter.print_diagnostic_summary(diagnostic_data, check_results)
        
        print(f"\n{GREEN}Full diagnostic saved to:{RESET} {log_file}")
        
        return diagnostic_data, check_results, log_file
    
    def setup_llm(self, use_container=True, model="llama3.1:8b"):
        """Set up LLM connection"""
        if use_container:
            # Check if container is running
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
        
        # Initialize LLM interface
        self.llm = LLMInterface(provider="ollama", model=model)
        
        # Check if LLM is available
        if not self.llm.is_available():
            print(f"{RED}❌ Cannot connect to Ollama{RESET}")
            if use_container:
                print("The container may not be ready yet. Please wait and try again.")
            else:
                print("Make sure Ollama is running: ollama serve")
            return False
        
        print(f"{GREEN}✅ Connected to Ollama{RESET}")
        
        # Check if model is available
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
        
        # Format data for LLM
        formatted_data = self.reporter.format_for_llm(diagnostic_data, check_results)
        
        # Get AI analysis
        llm_response, error = self.llm.analyze_diagnostics(formatted_data)
        
        if error:
            print(f"{RED}❌ AI analysis failed: {error}{RESET}")
            return None
        
        # Print AI analysis
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
        # Run initial diagnostic
        diagnostic_data, check_results, log_file = self.run_diagnostic(vm_name, failed_step)
        
        # Check if we should proceed with AI
        issues = check_results.get("issues", [])
        
        if not issues:
            print(f"\n{GREEN}No issues detected!{RESET}")
            print("If you're still experiencing problems, they may require manual investigation")
            return
        
        # Offer AI analysis
        print(f"\n{YELLOW}Would you like AI-assisted analysis?{RESET}")
        use_ai = input("Run AI troubleshooting? (yes/no): ").strip().lower()
        
        if use_ai not in ['yes', 'y']:
            print("Diagnostic complete. Check the report above for issues")
            return
        
        # Set up LLM
        print(f"\n{BLUE}Choose LLM source:{RESET}")
        print("1. Containerized Ollama (recommended)")
        print("2. Existing Ollama installation")
        
        choice = input("Enter choice (1/2): ").strip()
        
        use_container = choice != "2"
        
        # Ask for model preference
        print(f"\n{BLUE}Choose model:{RESET}")
        print("1. llama3.1:8b (Recommended - 8GB RAM)")
        print("2. llama3.2:3b (Faster - 4GB RAM)")
        print("3. mixtral:8x7b (Most accurate - 16GB RAM)")
        
        model_choice = input("Enter choice (1/2/3): ").strip()
        
        if model_choice == "2":
            model = "llama3.2:3b"
        elif model_choice == "3":
            model = "mixtral:8x7b"
        else:
            model = "llama3.1:8b"
        
        if not self.setup_llm(use_container, model):
            print(f"{RED}Failed to set up LLM{RESET}")
            return
        
        # Run AI analysis
        llm_response = self.run_ai_analysis(diagnostic_data, check_results)
        
        if not llm_response:
            return
        
        # Process recommendations
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