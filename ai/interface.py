"""
Provider-agnostic LLM interface
"""

from .ollama_client import OllamaClient
from .prompt import PromptBuilder
from .schema import ResponseParser

class LLMInterface:
    def __init__(self, provider="ollama", **kwargs):
        self.provider = provider
        self.prompt_builder = PromptBuilder()
        self.response_parser = ResponseParser()
        
        if provider == "ollama":
            base_url = kwargs.get("base_url", "http://localhost:11434")
            model = kwargs.get("model", "llama3.1:8b")
            self.client = OllamaClient(base_url=base_url, model=model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def is_available(self):
        """Check if LLM service is available"""
        return self.client.is_available()
    
    def list_models(self):
        """List available models"""
        return self.client.list_models()
    
    def ensure_model(self, model_name=None):
        """Ensure model is available, pull if necessary"""
        models = self.list_models()
        target_model = model_name or self.client.model
        
        if target_model not in models:
            print(f"\nModel '{target_model}' not found locally")
            print("Attempting to pull model...")
            success, message = self.client.pull_model(target_model)
            return success, message
        
        return True, "Model available"
    
    def analyze_diagnostics(self, formatted_data):
        """Analyze diagnostic data and return structured response"""
        prompt = self.prompt_builder.build_diagnostic_prompt(formatted_data)
        
        response_text, error = self.client.generate(
            prompt=prompt,
            system_prompt=self.prompt_builder.system_prompt,
            temperature=0.3,
            max_tokens=2000
        )
        
        if error:
            return None, error
        
        parsed_response, parse_error = self.response_parser.parse_llm_response(response_text)
        
        if parse_error:
            print(f"Warning: {parse_error}")
            # Still return the parsed response even if there were minor issues
        
        return parsed_response, None
    
    def analyze_followup(self, previous_response, new_info):
        """Analyze follow-up information after user action"""
        prompt = self.prompt_builder.build_followup_prompt(
            json.dumps(previous_response, indent=2),
            new_info
        )
        
        response_text, error = self.client.generate(
            prompt=prompt,
            system_prompt=self.prompt_builder.system_prompt,
            temperature=0.3,
            max_tokens=2000
        )
        
        if error:
            return None, error
        
        parsed_response, parse_error = self.response_parser.parse_llm_response(response_text)
        
        if parse_error:
            print(f"Warning: {parse_error}")
        
        return parsed_response, None