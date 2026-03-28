# gateway/ollama_client.py
"""Ollama API client for GABI Gateway."""

import json
import logging
import requests
from typing import Dict, Any, List, Optional, Union

from gateway.config import config

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Client for interacting with Ollama API.
    
    Supports:
    - Chat completions
    - Text generation
    - Model management (list, pull, delete)
    - Streaming responses
    - Vision models (with images)
    """
    
    def __init__(self, base_url: Optional[str] = None, default_model: Optional[str] = None):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama API base URL (default from config)
            default_model: Default model to use (default from config)
        """
        self.base_url = base_url or config.get_ollama_url()
        self.default_model = default_model or config.get("ollama.default_model", "llama2:latest")
        self.timeout = config.get("ollama.timeout", 60)
        
        logger.info(f"Ollama client initialized - URL: {self.base_url}, Default model: {self.default_model}")
    
    def _make_request(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        method: str = "POST",
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Make request to Ollama API.
        
        Args:
            endpoint: API endpoint (e.g., "/api/chat")
            data: Request data
            method: HTTP method (GET, POST, DELETE)
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON as dict
            
        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.timeout
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            elif method == "DELETE":
                response = requests.delete(url, timeout=timeout)
            else:
                response = requests.post(url, json=data, timeout=timeout)
            
            response.raise_for_status()
            
            # Handle streaming responses
            if endpoint == "/api/chat" and data and data.get("stream"):
                return response.text  # Return raw text for streaming
            
            return response.json()
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to Ollama at {self.base_url}")
            raise
        except requests.exceptions.Timeout:
            logger.error(f"Ollama request timeout after {timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise
    
    def chat(
        self,
        model: Optional[str] = None,
        messages: List[Dict[str, Any]] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request to Ollama.
        
        Args:
            model: Model name (default: default_model)
            messages: List of message dicts with role and content
            stream: Whether to stream response
            options: Additional model options (temperature, etc.)
            images: List of base64-encoded images for vision models
            **kwargs: Additional parameters
            
        Returns:
            Response dict with message and metadata
        """
        model = model or self.default_model
        
        data = {
            "model": model,
            "messages": messages or [],
            "stream": stream,
        }
        
        if options:
            data["options"] = options
        
        if images:
            # For vision models, images are attached to the last user message
            if data["messages"] and images:
                last_msg = data["messages"][-1]
                if last_msg.get("role") == "user":
                    last_msg["images"] = images
        
        data.update(kwargs)
        
        try:
            response = self._make_request("/api/chat", data)
            
            if stream:
                # Handle streaming response
                return {"stream": response, "model": model}
            
            return response
            
        except Exception as e:
            logger.error(f"Chat request failed: {e}")
            return {"error": str(e), "message": None}
    
    def generate(
        self,
        model: Optional[str] = None,
        prompt: str = "",
        system: Optional[str] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send generate completion request to Ollama.
        
        Args:
            model: Model name (default: default_model)
            prompt: Input prompt
            system: System prompt
            stream: Whether to stream response
            options: Additional model options
            images: List of base64-encoded images
            **kwargs: Additional parameters
            
        Returns:
            Response dict with response text and metadata
        """
        model = model or self.default_model
        
        data = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }
        
        if system:
            data["system"] = system
        
        if options:
            data["options"] = options
        
        if images:
            data["images"] = images
        
        data.update(kwargs)
        
        try:
            response = self._make_request("/api/generate", data)
            
            if stream:
                return {"stream": response, "model": model}
            
            return response
            
        except Exception as e:
            logger.error(f"Generate request failed: {e}")
            return {"error": str(e), "response": None}
    
    def list_models(self) -> Dict[str, Any]:
        """
        List available models.
        
        Returns:
            Dict with list of models
        """
        try:
            response = self._make_request("/api/tags", method="GET")
            return response
        except Exception as e:
            logger.error(f"List models failed: {e}")
            return {"models": []}
    
    def pull_model(
        self,
        model: str,
        stream: bool = False,
        callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Pull a model from Ollama registry.
        
        Args:
            model: Model name to pull
            stream: Whether to stream progress
            callback: Optional callback for streaming updates
            
        Returns:
            Response dict with status
        """
        data = {
            "name": model,
            "stream": stream
        }
        
        try:
            if stream and callback:
                # Handle streaming response
                url = f"{self.base_url}/api/pull"
                response = requests.post(url, json=data, stream=True, timeout=self.timeout)
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        callback(chunk)
                return {"status": "success", "model": model}
            else:
                response = self._make_request("/api/pull", data)
                return response
                
        except Exception as e:
            logger.error(f"Pull model failed: {e}")
            return {"status": "error", "error": str(e), "model": model}
    
    def delete_model(self, model: str) -> Dict[str, Any]:
        """
        Delete a model.
        
        Args:
            model: Model name to delete
            
        Returns:
            Response dict with status
        """
        data = {"name": model}
        
        try:
            response = self._make_request("/api/delete", data, method="DELETE")
            return {"status": "success", "model": model}
        except Exception as e:
            logger.error(f"Delete model failed: {e}")
            return {"status": "error", "error": str(e), "model": model}
    
    def show_model_info(self, model: str) -> Dict[str, Any]:
        """
        Get information about a model.
        
        Args:
            model: Model name
            
        Returns:
            Model information dict
        """
        data = {"name": model}
        
        try:
            response = self._make_request("/api/show", data)
            return response
        except Exception as e:
            logger.error(f"Show model info failed: {e}")
            return {"error": str(e)}
    
    def copy_model(self, source: str, destination: str) -> Dict[str, Any]:
        """
        Copy a model.
        
        Args:
            source: Source model name
            destination: Destination model name
            
        Returns:
            Response dict with status
        """
        data = {
            "source": source,
            "destination": destination
        }
        
        try:
            response = self._make_request("/api/copy", data)
            return {"status": "success", "source": source, "destination": destination}
        except Exception as e:
            logger.error(f"Copy model failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def is_available(self) -> bool:
        """
        Check if Ollama server is available.
        
        Returns:
            True if server is reachable
        """
        try:
            response = self._make_request("/api/tags", method="GET", timeout=5)
            return "models" in response
        except Exception:
            return False
    
    def get_model_size(self, model: str) -> Optional[int]:
        """
        Get model size in bytes.
        
        Args:
            model: Model name
            
        Returns:
            Model size in bytes or None
        """
        try:
            info = self.show_model_info(model)
            if info and "model_info" in info:
                # Different models have different size fields
                if "total_size" in info:
                    return info["total_size"]
                if "size" in info:
                    return info["size"]
            return None
        except Exception:
            return None
    
    def get_running_models(self) -> List[str]:
        """
        Get list of currently running models.
        
        Returns:
            List of running model names
        """
        try:
            response = self._make_request("/api/ps", method="GET")
            models = []
            for m in response.get("models", []):
                if m.get("name"):
                    models.append(m["name"])
            return models
        except Exception as e:
            logger.error(f"Get running models failed: {e}")
            return []
    
    def stop_model(self, model: str) -> Dict[str, Any]:
        """
        Stop a running model.
        
        Args:
            model: Model name to stop
            
        Returns:
            Response dict with status
        """
        data = {"name": model}
        
        try:
            response = self._make_request("/api/generate", data)
            return {"status": "success", "model": model}
        except Exception as e:
            logger.error(f"Stop model failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def create_embedding(self, model: str, input: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Create embeddings for text.
        
        Args:
            model: Model name (must support embeddings)
            input: Text or list of texts
            
        Returns:
            Embeddings response
        """
        data = {
            "model": model,
            "input": input
        }
        
        try:
            response = self._make_request("/api/embed", data)
            return response
        except Exception as e:
            logger.error(f"Create embedding failed: {e}")
            return {"error": str(e)}
    
    def stream_chat(
        self,
        model: Optional[str] = None,
        messages: List[Dict[str, Any]] = None,
        callback: Optional[callable] = None,
        **kwargs
    ) -> None:
        """
        Stream chat responses with callback.
        
        Args:
            model: Model name
            messages: List of messages
            callback: Function called with each chunk
            **kwargs: Additional parameters
        """
        model = model or self.default_model
        
        data = {
            "model": model,
            "messages": messages or [],
            "stream": True,
            **kwargs
        }
        
        try:
            url = f"{self.base_url}/api/chat"
            response = requests.post(url, json=data, stream=True, timeout=self.timeout)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if callback:
                        callback(chunk)
                    
                    # Check for done
                    if chunk.get("done", False):
                        break
                        
        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            if callback:
                callback({"error": str(e)})
    
    def stream_generate(
        self,
        model: Optional[str] = None,
        prompt: str = "",
        callback: Optional[callable] = None,
        **kwargs
    ) -> None:
        """
        Stream generate responses with callback.
        
        Args:
            model: Model name
            prompt: Input prompt
            callback: Function called with each chunk
            **kwargs: Additional parameters
        """
        model = model or self.default_model
        
        data = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            **kwargs
        }
        
        try:
            url = f"{self.base_url}/api/generate"
            response = requests.post(url, json=data, stream=True, timeout=self.timeout)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if callback:
                        callback(chunk)
                    
                    # Check for done
                    if chunk.get("done", False):
                        break
                        
        except Exception as e:
            logger.error(f"Stream generate failed: {e}")
            if callback:
                callback({"error": str(e)})


# Global client instance
ollama_client = OllamaClient()


def get_ollama_client() -> OllamaClient:
    """
    Get global Ollama client instance.
    
    Returns:
        Global OllamaClient instance
    """
    return ollama_client


def reset_ollama_client(base_url: Optional[str] = None, default_model: Optional[str] = None) -> OllamaClient:
    """
    Reset global client with new configuration.
    
    Args:
        base_url: New base URL
        default_model: New default model
        
    Returns:
        New OllamaClient instance
    """
    global ollama_client
    ollama_client = OllamaClient(base_url, default_model)
    return ollama_client