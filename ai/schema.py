"""
Response parsing and validation
"""

import json
import re

class ResponseParser:
    def __init__(self):
        pass
    
    def parse_llm_response(self, response_text):
        """Parse LLM response and extract structured data"""
        if not response_text:
            return None, "Empty response from LLM"
        
        # Try to extract JSON from the response
        # LLMs sometimes wrap JSON in markdown code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            else:
                # No JSON found, treat entire response as diagnosis
                return {
                    "confidence": 50,
                    "diagnosis": response_text,
                    "recommendations": []
                }, None
        
        try:
            data = json.loads(json_text)
            
            # Validate structure
            if not isinstance(data, dict):
                return None, "Response is not a JSON object"
            
            # Ensure required fields
            result = {
                "confidence": self._validate_confidence(data.get("confidence", 50)),
                "diagnosis": data.get("diagnosis", "No diagnosis provided"),
                "recommendations": self._validate_recommendations(data.get("recommendations", []))
            }
            
            return result, None
        
        except json.JSONDecodeError as e:
            # Fallback: treat as plain text
            return {
                "confidence": 40,
                "diagnosis": response_text,
                "recommendations": []
            }, f"JSON parsing failed: {str(e)}"
    
    def _validate_confidence(self, confidence):
        """Ensure confidence is a valid number 0-100"""
        try:
            conf = int(confidence)
            return max(0, min(100, conf))
        except (ValueError, TypeError):
            return 50
    
    def _validate_recommendations(self, recommendations):
        """Validate and clean up recommendations"""
        if not isinstance(recommendations, list):
            return []
        
        validated = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            
            validated_rec = {
                "description": rec.get("description", "No description"),
                "command": rec.get("command"),
                "explanation": rec.get("explanation", "")
            }
            validated.append(validated_rec)
        
        return validated
    
    def extract_commands(self, parsed_response):
        """Extract all commands from recommendations"""
        commands = []
        recommendations = parsed_response.get("recommendations", [])
        
        for rec in recommendations:
            cmd = rec.get("command")
            if cmd and cmd.strip():
                commands.append({
                    "command": cmd.strip(),
                    "description": rec.get("description", ""),
                    "explanation": rec.get("explanation", "")
                })
        
        return commands