"""
Ollama client for local and containerized LLM inference
"""

import requests
import json
import time

class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="llama3.1:8b"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = 120  # 2 minutes timeout for inference
    
    def is_available(self):
        """Check if Ollama is running and accessible"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def list_models(self):
        """List available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            return []
        except:
            return []
    
    def pull_model(self, model_name=None, progress_callback=None):
        """Pull a model from Ollama registry"""
        model_to_pull = model_name or self.model
        
        try:
            print(f"Pulling model: {model_to_pull}")
            print("This may take several minutes depending on model size...")
            
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_to_pull},
                stream=True,
                timeout=600  # 10 minutes for download
            )
            
            if response.status_code != 200:
                return False, f"Failed to pull model: HTTP {response.status_code}"
            
            # Stream progress
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        status = data.get('status', '')
                        
                        if progress_callback:
                            progress_callback(data)
                        else:
                            # Simple progress output
                            if 'total' in data and 'completed' in data:
                                total = data['total']
                                completed = data['completed']
                                percent = (completed / total * 100) if total > 0 else 0
                                print(f"\r{status}: {percent:.1f}%", end='', flush=True)
                            else:
                                print(f"\r{status}", end='', flush=True)
                        
                        if status == 'success':
                            print("\n✅ Model pulled successfully")
                            return True, "Success"
                    except json.JSONDecodeError:
                        continue
            
            return True, "Success"
        
        except Exception as e:
            return False, f"Error pulling model: {str(e)}"
    
    def generate(self, prompt, system_prompt=None, temperature=0.3, max_tokens=2000):
        """Generate a response from the LLM"""
        if not self.is_available():
            return None, "Ollama is not available"
        
        # Check if model exists
        available_models = self.list_models()
        if not available_models:
            return None, "No models available. Please pull a model first."
        
        if self.model not in available_models:
            return None, f"Model {self.model} not found. Available models: {', '.join(available_models)}"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        try:
            print(f"Sending request to LLM ({self.model})...")
            print("This may take 30-60 seconds depending on system specs...")
            
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            elapsed = time.time() - start_time
            
            if response.status_code != 200:
                return None, f"LLM request failed: HTTP {response.status_code}"
            
            data = response.json()
            response_text = data.get('response', '')
            
            print(f"✅ Response received ({elapsed:.1f}s)")
            
            return response_text, None
        
        except requests.Timeout:
            return None, "LLM request timed out. The model may be too large for your system."
        except Exception as e:
            return None, f"Error generating response: {str(e)}"
    
    def chat(self, messages, temperature=0.3, max_tokens=2000):
        """Chat interface (for future use)"""
        if not self.is_available():
            return None, "Ollama is not available"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return None, f"LLM request failed: HTTP {response.status_code}"
            
            data = response.json()
            return data.get('message', {}).get('content', ''), None
        
        except Exception as e:
            return None, f"Error in chat: {str(e)}"