# integrations/semantic_memory.py
"""Semantic memory with vector search."""

import json
import numpy as np
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SemanticMemory:
    """Semantic memory with simple vector search."""
    
    def __init__(self, memory_file: str = "semantic_memory.json"):
        self.memory_file = Path(memory_file)
        self.entries: List[Dict[str, Any]] = []
        self._load_memory()
    
    def _load_memory(self):
        """Load memory from file."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entries = data.get("entries", [])
                logger.info(f"Loaded {len(self.entries)} semantic entries")
            except Exception as e:
                logger.error(f"Load semantic memory error: {e}")
    
    def _save_memory(self):
        """Save memory to file."""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump({"entries": self.entries}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Save semantic memory error: {e}")
    
    def _text_to_vector(self, text: str) -> np.ndarray:
        """Convert text to simple hash-based vector."""
        # Simple character-based vector
        vector = np.zeros(100)
        for i, char in enumerate(text[:1000]):
            idx = (hash(char) % 100)
            vector[idx] += 1
        return vector / (len(text) + 1)
    
    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0
        return np.dot(v1, v2) / (norm1 * norm2)
    
    def add_knowledge(self, text: str, metadata: Dict[str, Any] = None) -> None:
        """Add knowledge to memory."""
        text = text.strip()
        if not text:
            return
        
        # Check for duplicates
        text_hash = hashlib.md5(text.encode()).hexdigest()
        for entry in self.entries:
            if entry.get("hash") == text_hash:
                return
        
        vector = self._text_to_vector(text)
        
        self.entries.append({
            "hash": text_hash,
            "text": text,
            "vector": vector.tolist(),
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat()
        })
        
        # Limit entries
        if len(self.entries) > 1000:
            self.entries = self.entries[-1000:]
        
        self._save_memory()
        logger.debug(f"Added knowledge: {text[:50]}...")
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar knowledge."""
        if not self.entries:
            return []
        
        query_vector = self._text_to_vector(query)
        
        results = []
        for entry in self.entries:
            entry_vector = np.array(entry.get("vector", []))
            if len(entry_vector) > 0:
                score = self._cosine_similarity(query_vector, entry_vector)
                results.append({
                    "text": entry["text"],
                    "metadata": entry.get("metadata", {}),
                    "score": float(score)
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def get_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all entries."""
        return self.entries[-limit:]
    
    def clear(self):
        """Clear all memory."""
        self.entries = []
        self._save_memory()
        logger.info("Semantic memory cleared")