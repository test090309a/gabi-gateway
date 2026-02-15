"""FastAPI HTTP endpoints."""
import logging
import platform
import shutil
import subprocess
from gateway.config import config

from typing import Any
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel # Neu importiert

from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from integrations.shell_executor import shell_executor
from integrations.gmail_client import get_gmail_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Definition des Datenmodells für die Shell
class ShellRequest(BaseModel):
    command: str
    args: Optional[List[str]] = []

# Einfacher Schutz über den API-Key aus deiner Config
async def verify_token(x_api_key: str = Header(None)):
    if x_api_key != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Ungültiger API-Key")
    return x_api_key


# ============ Ollama Chat Endpoints ============

@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """OpenAI-compatible /v1/chat/completions endpoint."""
    model = payload.get("model", ollama_client.default_model)
    messages = payload.get("messages", [])

    try:
        response = ollama_client.chat(model=model, messages=messages)
        return {
            "id": f"chatcmpl-{response.get('id', 'unknown')}",
            "object": "chat.completion",
            "created": response.get("created", 0),
            "model": model,
            "choices": [{
                "index": 0,
                "message": response.get("message", {}),
                "finish_reason": response.get("done", True) and "stop" or "length",
            }],
            "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        }
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/models")
async def list_models(_api_key: str = Depends(verify_api_key)) -> dict[str, Any]:
    """List available Ollama models."""
    try:
        result = ollama_client.list_models()
        return {
            "object": "list",
            "data": [{
                "id": m.get("name", ""),
                "object": "model",
                "created": 0,
                "owned_by": "ollama",
            } for m in result.get("models", [])],
        }
    except Exception as e:
        logger.error(f"List models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Shell Executor Endpoints ============


@router.post("/api/shell/execute")
async def execute_shell(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Execute a shell command from allowlist."""
    command = payload.get("command")
    args = payload.get("args", [])

    if not command:
        raise HTTPException(status_code=400, detail="Command is required")

    try:
        result = shell_executor.execute(command, args)
        return result
    except PermissionError as e:
        logger.warning(f"Shell permission denied: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except Exception as e:
        logger.error(f"Shell execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/shell/allowed")
async def list_allowed_commands(_api_key: str = Depends(verify_api_key)) -> dict:
    """List allowed shell commands."""
    return {"allowed_commands": shell_executor.get_allowed_commands()}


# ============ Gmail Endpoints ============


@router.get("/api/gmail/mails")
async def list_gmail_messages(
    max_results: int = 10,
    query: str = "",
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List Gmail messages."""
    try:
        messages = get_gmail_client().list_messages(max_results=max_results, query=query)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        logger.error(f"Gmail list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/gmail/mail/{message_id}")
async def get_gmail_message(
    message_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Get a specific Gmail message."""
    try:
        client = get_gmail_client()
        message = client.get_message(message_id)
        body = client.get_message_body(message)
        return {"message": message, "body": body}
    except Exception as e:
        logger.error(f"Gmail get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/gmail/send")
async def send_gmail_message(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Send a Gmail message."""
    to = payload.get("to")
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if not to:
        raise HTTPException(status_code=400, detail="Recipient 'to' is required")

    try:
        result = get_gmail_client().send_message(to, subject, body)
        return {"success": True, "message_id": result.get("id")}
    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/gmail/mail/{message_id}/modify")
async def modify_gmail_message(
    message_id: str,
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Modify Gmail message labels (archive, star, etc.)."""
    add_labels = payload.get("add_labels")
    remove_labels = payload.get("remove_labels")

    try:
        result = get_gmail_client().modify_message(message_id, add_labels, remove_labels)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Gmail modify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Health Check ============


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}

@router.get("/status")
async def get_status():
    """Zeigt den System- und Dienst-Status an."""
    ollama_ok = False
    models = []
    try:
        models_info = ollama_client.list_models()
        models = [m.get("name") for m in models_info.get("models", [])]
        ollama_ok = True
    except Exception:
        ollama_ok = False

    _, used, free = shutil.disk_usage("/")
    
    return {
        "gateway": "online",
        "system": {
            "os": platform.system(),
            "version": platform.release(),
            "storage_free_gb": round(free / (2**30), 2),
        },
        "services": {
            "ollama": {
                "status": "connected" if ollama_ok else "offline",
                "available_models": models
            },
            "telegram": {
                "enabled": config.get("telegram.enabled", False)
            }
        }
    }

@router.post("/shell")
async def execute_command(request: ShellRequest, token: str = Header(None)):
    """
    Führt erlaubte Shell-Befehle aus der config.yaml aus.
    Erwartet 'token' im Header und JSON Body mit 'command' und 'args'.
    """
    # Sicherheitscheck: Token prüfen (dein 'sysop' aus der config)
    if token != config.get("api_key"):
        logger_token = token if token else "Kein Token"
        raise HTTPException(status_code=403, detail=f"Access Denied: Falscher API-Key ({logger_token})")

    allowed_commands = config.get("shell.allowed_commands", [])
    
    # Sicherheitscheck: Ist der Befehl in der Liste erlaubt?
    if request.command not in allowed_commands:
        raise HTTPException(status_code=400, detail=f"Befehl '{request.command}' nicht erlaubt!")

    try:
        # Befehl zusammenbauen
        full_cmd = [request.command] + request.args
        
        # Ausführung optimiert für Windows 11 Admins
        result = subprocess.run(
            full_cmd, 
            capture_output=True, 
            text=True, 
            shell=True, 
            timeout=15, # Auf 15s erhöht für schwerfällige Windows-Befehle
            encoding='cp850' # Korrigiert Sonderzeichen in der CMD-Ausgabe
        )
        
        return {
            "status": "success",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error", 
            "message": f"Befehl '{request.command}' lief in den Timeout (15s)."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}