# gateway/utils/model_helpers.py
"""Hilfsfunktionen für Modell-Operationen (Ollama, Vision, etc.)."""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


def _extract_ollama_text(payload: Any) -> str:
    """
    Extract textual content from varied Ollama response shapes.
    
    Args:
        payload: Ollama response (can be dict, list, or string)
        
    Returns:
        Extracted text as string
    """
    if payload is None:
        return ""
    
    if isinstance(payload, str):
        return payload.strip()
    
    if isinstance(payload, dict):
        # Check for message field
        if "message" in payload:
            return _extract_ollama_text(payload.get("message"))
        
        # Check for response field
        if isinstance(payload.get("response"), str):
            return payload.get("response", "").strip()
        
        # Check for content field
        content = payload.get("content")
        if isinstance(content, str):
            return content.strip()
        
        # Check for list content (e.g., in streaming responses)
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text") or item.get("content") or ""
                    if text_value:
                        chunks.append(str(text_value))
            return "\n".join(chunks).strip()
        
        return ""
    
    if isinstance(payload, list):
        chunks = [_extract_ollama_text(item) for item in payload]
        return "\n".join([c for c in chunks if c]).strip()
    
    return str(payload).strip()


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse first JSON object from a raw model response.
    
    Args:
        raw: Raw string that may contain JSON
        
    Returns:
        Parsed JSON dict or None if not found
    """
    if not raw:
        return None
    
    text = raw.strip()
    
    # Remove markdown code blocks
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    
    # Try direct JSON parsing
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    
    # Try to extract first JSON object with regex
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    
    return None


def _extract_model_score(name: str) -> float:
    """
    Heuristic score for model size from its name.
    Supports formats like 1.2b, 24b, 70b, etc.
    
    Args:
        name: Model name (e.g., "llama2:7b", "qwen2.5:14b")
        
    Returns:
        Float representing model size in billions of parameters
    """
    if not name:
        return 0.0
    
    lowered = name.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*b", lowered)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0


def _infer_model_capabilities(name: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Infer practical model capabilities from model name/details.
    
    Args:
        name: Model name
        details: Optional model details dict
        
    Returns:
        Dict with capability flags (vision, tools, etc.)
    """
    lowered = (name or "").lower()
    details_text = json.dumps(details or {}, ensure_ascii=False).lower()
    merged = f"{lowered} {details_text}"
    
    # Vision capability hints
    vision_hints = [
        "vl", "vision", "llava", "moondream", "minicpm-v", 
        "internvl", "qwen2.5vl", "qwen2-vl", "bakllava",
        "cambrian", "phi3-vision", "llama3.2-vision", "paligemma",
        "cogvlm", "glm-4v", "qwen3-vl"
    ]
    
    # Tool/Function calling hints
    tool_hints = ["tool", "function", "json"]
    
    supports_vision = any(hint in merged for hint in vision_hints)
    supports_tools = any(hint in merged for hint in tool_hints)
    
    return {
        "vision": supports_vision,
        "tools": supports_tools,
    }


def _is_vision_model(model_name: str) -> bool:
    """
    Check if a model is vision-capable.
    
    Args:
        model_name: Name of the model
        
    Returns:
        True if model likely supports vision
    """
    caps = _infer_model_capabilities(model_name)
    return caps.get("vision", False)


def _pick_best_model(
    available: List[str],
    hints: Optional[List[str]] = None,
    min_size: float = 0.0,
    max_size: Optional[float] = None,
) -> Optional[str]:
    """
    Pick strongest model by optional hints and minimum size.
    
    Args:
        available: List of available model names
        hints: Optional list of hint strings to prefer
        min_size: Minimum model size in billions of parameters
        max_size: Maximum model size in billions of parameters
        
    Returns:
        Best model name or None
    """
    if not available:
        return None
    
    pool = available
    
    # Filter by hints
    if hints:
        hinted = [m for m in available if any(hint in m.lower() for hint in hints)]
        if hinted:
            pool = hinted
    
    # Filter by minimum size
    if min_size > 0:
        strong = [m for m in pool if _extract_model_score(m) >= min_size]
        if strong:
            pool = strong
    
    # Filter by maximum size
    if max_size and max_size > 0:
        capped = [m for m in pool if 0 < _extract_model_score(m) <= max_size]
        if capped:
            pool = capped
    
    # Sort by size descending and return first
    if pool:
        return sorted(pool, key=_extract_model_score, reverse=True)[0]
    
    return None


def _pick_fast_model(available: List[str]) -> Optional[str]:
    """
    Pick a fast/small model for routing/self-check tasks.
    
    Args:
        available: List of available model names
        
    Returns:
        Fast model name or None
    """
    if not available:
        return None
    
    # Fast model hints (small, fast models)
    fast_hints = [
        "lfm", "mini", "small", "tiny", "phi", "gemma:2b", 
        "1.5b", "1.2b", "2b", "3b", "qwen2.5:1.5b", "llama3.2:3b"
    ]
    
    fast_candidates = [m for m in available if any(hint in m.lower() for hint in fast_hints)]
    
    if not fast_candidates:
        fast_candidates = available
    
    # Prefer smaller models; unknown size gets lowest priority
    def fast_key(name: str) -> float:
        score = _extract_model_score(name)
        return score if score > 0 else 9999.0
    
    return sorted(fast_candidates, key=fast_key)[0] if fast_candidates else None


def _pick_preferred_available(available: List[str], preferred: List[str]) -> Optional[str]:
    """
    Pick first preferred model present in available list.
    
    Args:
        available: List of available model names
        preferred: List of preferred model names/hints
        
    Returns:
        Matching model name or None
    """
    if not available or not preferred:
        return None
    
    # Exact matches (case-insensitive)
    available_by_lower = {m.lower(): m for m in available}
    for pref in preferred:
        exact = available_by_lower.get(pref.lower())
        if exact:
            return exact
    
    # Fuzzy matches (contains)
    for pref in preferred:
        pref_l = pref.lower()
        for model in available:
            if pref_l in model.lower():
                return model
    
    return None


def _as_model_pref_list(raw: Any) -> List[str]:
    """
    Normalize model preference setting to a list of non-empty strings.
    
    Args:
        raw: Raw preference value (string, list, or None)
        
    Returns:
        List of model names
    """
    if raw is None:
        return []
    
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    
    text = str(raw).strip()
    if not text:
        return []
    
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    
    return [text]


def _get_model_size_gb(model_name: str) -> float:
    """
    Estimate model size in GB based on parameter count.
    
    Args:
        model_name: Model name
        
    Returns:
        Estimated size in GB (float)
    """
    param_count = _extract_model_score(model_name)
    if param_count <= 0:
        return 0.0
    
    # Rough estimate: 1B params ≈ 4GB for 16-bit, 2GB for 8-bit
    # Using conservative 4GB per billion
    return param_count * 4.0


def _is_small_model(model_name: str, max_size_gb: float = 8.0) -> bool:
    """
    Check if model is small enough for resource-constrained environments.
    
    Args:
        model_name: Model name
        max_size_gb: Maximum acceptable size in GB
        
    Returns:
        True if model is small enough
    """
    size_gb = _get_model_size_gb(model_name)
    return 0 < size_gb <= max_size_gb


def _get_model_recommendation(task: str, available: List[str]) -> Optional[str]:
    """
    Get model recommendation based on task type.
    
    Args:
        task: Task type ("code", "vision", "chat", "analysis")
        available: List of available models
        
    Returns:
        Recommended model name or None
    """
    if not available:
        return None
    
    task_lower = task.lower()
    
    # Code tasks
    if task_lower in ["code", "programming", "coding"]:
        code_hints = ["coder", "code", "codellama", "starcoder", "deepseek-coder", "qwen2.5-coder"]
        return _pick_best_model(available, hints=code_hints, min_size=7.0)
    
    # Vision tasks
    if task_lower in ["vision", "image", "analyze"]:
        vision_hints = ["vl", "vision", "llava", "qwen2.5vl", "moondream"]
        return _pick_best_model(available, hints=vision_hints)
    
    # Analysis tasks (need good reasoning)
    if task_lower in ["analysis", "reasoning", "complex"]:
        return _pick_best_model(available, min_size=7.0)
    
    # Default: fast model for simple tasks
    if task_lower in ["chat", "simple"]:
        return _pick_fast_model(available)
    
    return None


def _format_model_response(model_name: str, response_text: str, max_length: int = 2000) -> str:
    """
    Format model response for display.
    
    Args:
        model_name: Name of the model
        response_text: Raw response text
        max_length: Maximum length of response
        
    Returns:
        Formatted response string
    """
    if not response_text:
        return "⚠️ Keine Antwort erhalten."
    
    # Truncate if too long
    if len(response_text) > max_length:
        response_text = response_text[:max_length] + "\n\n... (Antwort gekürzt)"
    
    return response_text


def _validate_model_name(model_name: str, available: List[str]) -> bool:
    """
    Validate if a model name is available.
    
    Args:
        model_name: Model name to validate
        available: List of available models
        
    Returns:
        True if model is available
    """
    if not model_name:
        return False
    
    return model_name in available or any(m.startswith(model_name) for m in available)


# Alias for backward compatibility
def extract_ollama_text(payload: Any) -> str:
    """Alias for _extract_ollama_text."""
    return _extract_ollama_text(payload)


def extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Alias for _extract_json_object."""
    return _extract_json_object(raw)


def infer_model_capabilities(name: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Alias for _infer_model_capabilities."""
    return _infer_model_capabilities(name, details)


def get_model_size_gb(model_name: str) -> float:
    """Alias for _get_model_size_gb."""
    return _get_model_size_gb(model_name)