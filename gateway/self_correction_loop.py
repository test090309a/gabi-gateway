# gateway/self_correction_loop.py - Optimierte Version mit Parallelisierung
import logging
import json
import re
import time
import asyncio
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import functools

from gateway.config import config
from gateway.ollama_client import ollama_client

logger = logging.getLogger("GATEWAY.self_correction")

# Konstanten
DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MIN_SCORE_THRESHOLD = 0.7
CACHE_TTL = 3600  # 1 Stunde Cache

# Task-spezifische Thresholds
TASK_THRESHOLDS = {
    "chat": 0.6,      # Chat kann toleranter sein
    "code": 0.85,     # Code muss sehr gut sein
    "analysis": 0.75, # Analyse mittlere Genauigkeit
    "creative": 0.65  # Kreativaufgaben mehr Spielraum
}

# Verbesserter Evaluator-Prompt mit strukturiertem Feedback
EVALUATOR_SYSTEM_PROMPT = """Du bist der GABI-Qualitätskontrolleur.
Analysiere die Antworten und antworte AUSSCHLIESSLICH im JSON-Format.

Bewertungskriterien:
- Genauigkeit (0-1): Wie präzise ist die Antwort?
- Vollständigkeit (0-1): Wurde alles beantwortet?
- Qualität (0-1): Struktur, Klarheit, Verständlichkeit
- Kontext (0-1): Passt die Antwort zum Kontext?

Struktur:
{
  "best_answer_index": 1,
  "score": 0.85,
  "dimensions": {
    "accuracy": 0.9,
    "completeness": 0.8,
    "quality": 0.85,
    "context": 0.85
  },
  "reasoning": "Kurze Begründung für die Wahl",
  "critique": "Was genau ist verbesserungswürdig?",
  "improvement_instructions": "Konkrete Anweisungen für die Verbesserung",
  "learning_points": ["Wichtige Erkenntnis 1", "Wichtige Erkenntnis 2"]
}"""

class ResponseCache:
    """Semantischer Cache für wiederholte Anfragen"""
    def __init__(self, ttl=CACHE_TTL):
        self.cache = {}
        self.ttl = ttl
        self.timestamps = {}
    
    def _get_key(self, prompt: str, model: str, context: str = "") -> str:
        """Erstelle Cache-Key basierend auf Prompt und Kontext"""
        content = f"{prompt}|{model}|{context}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, prompt: str, model: str, context: str = "") -> Optional[Dict]:
        key = self._get_key(prompt, model, context)
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.timestamps[key]
        return None
    
    def set(self, prompt: str, model: str, response: Dict, context: str = ""):
        key = self._get_key(prompt, model, context)
        self.cache[key] = response
        self.timestamps[key] = time.time()

class SelfCorrectionLoop:
    def __init__(self):
        self.config = self._load_config()
        self.max_iterations = self.config.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        self.min_score_threshold = self.config.get("min_score_threshold", DEFAULT_MIN_SCORE_THRESHOLD)
        self.evaluator_model = self._get_evaluator_model()
        self.cache = ResponseCache()
        self.executor = ThreadPoolExecutor(max_workers=4)  # Für parallele Abfragen
        
        # Performance Metriken
        self.metrics = {
            "total_iterations": 0,
            "avg_latency": 0,
            "cache_hits": 0,
            "total_calls": 0
        }
        
        logger.info(f"Self-Correction Loop optimiert (Evaluator: {self.evaluator_model})")

    def _load_config(self) -> Dict[str, Any]:
        return config.get("self_correction", {})

    def _get_evaluator_model(self) -> str:
        return self.config.get("evaluator_model", "llama3.1:8b")
    
    def _get_task_threshold(self, task_type: str) -> float:
        """Adaptive Threshold basierend auf Task-Typ"""
        return TASK_THRESHOLDS.get(task_type, self.min_score_threshold)
    
    def _query_model_parallel(self, model: str, prompt: str, context: str = "") -> Tuple[str, Dict]:
        """Parallele Abfrage mit Caching"""
        start_time = time.time()
        self.metrics["total_calls"] += 1
        
        # Cache check
        cached = self.cache.get(prompt, model, context)
        if cached:
            self.metrics["cache_hits"] += 1
            logger.debug(f"Cache hit for model {model}")
            return model, cached
        
        try:
            res = ollama_client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            response = res.get("message", {}).get("content", "")
            
            # Cache speichern
            self.cache.set(prompt, model, {"content": response, "timestamp": time.time()}, context)
            
            latency = time.time() - start_time
            logger.debug(f"Model {model} responded in {latency:.2f}s")
            
            return model, {"content": response, "latency": latency}
        except Exception as e:
            logger.error(f"Error querying {model}: {e}")
            return model, {"content": "", "error": str(e)}

    def process(self, prompt: str, task_type: str = "chat", **kwargs) -> Dict[str, Any]:
        """Hauptprozess mit Parallelisierung und adaptivem Lernen"""
        start_total = time.time()
        iterations_used = 0
        current_prompt = prompt
        best_response = ""
        current_score = 0.0
        thinking_steps = []
        response_history = []
        
        # Adaptive Threshold für diese Task
        threshold = self._get_task_threshold(task_type)
        logger.info(f"Processing {task_type} task with threshold {threshold}")
        
        # Modelle basierend auf Task wählen
        models = self._get_task_models(task_type)
        
        for i in range(self.max_iterations):
            iteration_start = time.time()
            iterations_used += 1
            
            # **PARALLELE MODELL-ABFRAGEN**
            thinking_steps.append({
                "step": f"Runde {iterations_used}: Parallele Abfrage von {len(models)} Modellen",
                "type": "info",
                "timestamp": datetime.now().isoformat()
            })
            
            # Parallele Abfragen mit ThreadPool
            futures = []
            for model in models:
                future = self.executor.submit(
                    self._query_model_parallel, 
                    model, 
                    current_prompt,
                    task_type  # Kontext für Cache
                )
                futures.append(future)
            
            # Ergebnisse sammeln
            responses = []
            for future in as_completed(futures):
                model, result = future.result()
                if result.get("content"):
                    responses.append(result["content"])
            
            if not responses:
                logger.error("No valid responses received")
                break
            
            # **OPTIMIERTE EVALUATION**
            eval_data = self._evaluate(responses, prompt, task_type)
            idx = max(0, min(eval_data.get("best_answer_index", 1) - 1, len(responses) - 1))
            
            current_score = float(eval_data.get("score", 0.5))
            best_response = responses[idx]
            
            # Speichere für Lernanalyse
            response_history.append({
                "iteration": i,
                "score": current_score,
                "response": best_response[:200],  # Nur Preview
                "critique": eval_data.get("critique", "")
            })
            
            thinking_steps.append({
                "step": f"Bewertung: {current_score:.3f} | {eval_data.get('reasoning')}",
                "type": "evaluator",
                "dimensions": eval_data.get("dimensions", {}),
                "timestamp": datetime.now().isoformat()
            })
            
            iteration_latency = time.time() - iteration_start
            thinking_steps.append({
                "step": f"Runde {iterations_used} fertig in {iteration_latency:.2f}s",
                "type": "performance",
                "timestamp": datetime.now().isoformat()
            })
            
            # **ADAPTIVER ABBRUCH**
            if current_score >= threshold:
                logger.info(f"Reached threshold {threshold} after {iterations_used} iterations")
                break
            
            # **STRUKTURIERTES FEEDBACK**
            if i < self.max_iterations - 1:  # Nicht in letzter Runde
                current_prompt = self._build_improved_prompt(
                    best_response, 
                    eval_data,
                    response_history
                )
        
        # Metriken aktualisieren
        total_latency = time.time() - start_total
        self.metrics["total_iterations"] += iterations_used
        self.metrics["avg_latency"] = (
            (self.metrics["avg_latency"] * (self.metrics["total_iterations"] - iterations_used) + total_latency) 
            / self.metrics["total_iterations"]
        )
        
        # Lernerfahrung extrahieren
        learning_insights = self._extract_learning_insights(response_history)
        
        return {
            "response": best_response,
            "best_score": current_score,
            "iterations_used": iterations_used,
            "total_latency": total_latency,
            "threshold_used": threshold,
            "thinking_steps": thinking_steps,
            "model_used": self.evaluator_model,
            "learning_insights": learning_insights,
            "metrics": {
                "cache_hit_rate": self.metrics["cache_hits"] / max(1, self.metrics["total_calls"]),
                "avg_latency": self.metrics["avg_latency"]
            }
        }

    def _evaluate(self, responses: List[str], original_prompt: str, task_type: str) -> Dict[str, Any]:
        """Optimierte Evaluation mit Task-Kontext"""
        eval_input = f"Aufgabentyp: {task_type}\nFrage: {original_prompt}\n\n"
        for i, r in enumerate(responses):
            eval_input += f"Entwurf {i+1}:\n{r[:500]}\n\n"  # Limit für Performance
        
        try:
            res = ollama_client.chat(
                model=self.evaluator_model,
                messages=[
                    {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": eval_input}
                ],
                format="json"
            )
            
            content = res.get("message", {}).get("content", "{}")
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Evaluation Error: {e}")
            return {
                "score": 0.5, 
                "best_answer_index": 1, 
                "reasoning": f"Fehler: {str(e)}",
                "critique": "Fallback evaluation",
                "improvement_instructions": "Versuche es mit einem anderen Ansatz"
            }

    def _build_improved_prompt(self, best_response: str, eval_data: Dict, history: List) -> str:
        """Baut strukturiertes Feedback für nächste Iteration"""
        critique = eval_data.get("critique", "Verbessere die Antwort")
        instructions = eval_data.get("improvement_instructions", "Mache die Antwort präziser")
        learning_points = eval_data.get("learning_points", [])
        
        # Historische Fehler einbeziehen
        past_mistakes = []
        for h in history[-2:]:  # Letzte 2 Fehler
            if h.get("critique"):
                past_mistakes.append(h["critique"])
        
        feedback = f"""Dein letzter Entwurf hatte folgende Probleme:
{critique}

Konkrete Verbesserungsanweisungen:
{instructions}

"""
        if past_mistakes:
            feedback += f"\nVermeide wiederholte Fehler:\n- " + "\n- ".join(past_mistakes[-2:])
        
        if learning_points:
            feedback += f"\n\nWichtige Erkenntnisse:\n- " + "\n- ".join(learning_points)
        
        return f"{best_response}\n\n[FEEDBACK ZUR VERBESSERUNG]\n{feedback}\n\nBitte erstelle eine verbesserte Version."

    def _extract_learning_insights(self, history: List) -> Dict:
        """Extrahiert Lernmuster aus der Historie"""
        if len(history) < 2:
            return {"improvement_rate": 0, "common_issues": []}
        
        scores = [h["score"] for h in history]
        improvement = scores[-1] - scores[0] if scores else 0
        
        # Extrahiere wiederkehrende Kritikpunkte
        critiques = [h.get("critique", "") for h in history if h.get("critique")]
        
        return {
            "improvement_rate": improvement,
            "score_progression": scores,
            "common_issues": list(set(critiques))[:3],  # Top 3 einzigartige Issues
            "iterations_needed": len(history)
        }

    def _get_task_models(self, task_type: str) -> List[str]:
        """Optimierte Modellauswahl"""
        ollama_cfg = config.get("ollama", {})
        
        if task_type == "code":
            return ollama_cfg.get("preferred_code_models", ["qwen2.5-coder:14b", "qwen3-coder:latest"])[:2]
        elif task_type == "analysis":
            return ollama_cfg.get("preferred_analysis_models", ["llama3.1:8b", "qwen2.5-coder:14b"])[:2]
        else:  # chat, creative
            return ollama_cfg.get("preferred_creative_models", ["llama3.1:8b", "qwen2.5-coder:14b"])[:2]

    def get_performance_report(self) -> Dict:
        """Gibt Performance-Metriken zurück"""
        return {
            **self.metrics,
            "cache_efficiency": self.metrics["cache_hits"] / max(1, self.metrics["total_calls"]),
            "avg_iterations_per_task": self.metrics["total_iterations"] / max(1, self.metrics["total_calls"])
        }

# === SINGLETON INSTANCE ===
_correction_instance: Optional[SelfCorrectionLoop] = None

def get_correction_loop() -> SelfCorrectionLoop:
    global _correction_instance
    if _correction_instance is None:
        _correction_instance = SelfCorrectionLoop()
    return _correction_instance

def process_with_correction(prompt: str, task_type: str = "chat", **kwargs) -> Dict[str, Any]:
    return get_correction_loop().process(prompt, task_type, **kwargs)

def get_performance_report() -> Dict:
    return get_correction_loop().get_performance_report()