# Gateway Projekt - Minimalistisches Ollama-Gateway mit Integrationen

## Installation

```bash
pip install -r requirements.txt
```

## Konfiguration

Kopiere `config.example.yaml` nach `config.yaml` und passe sie an:

```yaml
# Server
host: "0.0.0.0"
port: 8000
api_key: "dein-geheimer-api-key"

# Ollama
ollama:
  base_url: "http://localhost:11434"
  default_model: "llama3.2"

# Telegram
telegram:
  bot_token: "DEIN_BOT_TOKEN"

# Gmail
gmail:
  credentials_path: "credentials.json"
  token_path: "token.json"

# Shell-Commands (Allowlist)
shell:
  allowed_commands:
    - "ls"
    - "pwd"
    - "date"
    - "echo"
    - "cat"
    - "git"
```

## Gmail OAuth2 einrichten

1. Google Cloud Console → Credentials → OAuth2 Client ID
2. Desktop-App konfigurieren
3. `credentials.json` herunterladen und in Projektverzeichnis legen
4. Beim ersten Start wird OAuth-Flow automatisch gestartet

## Starten

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API-Endpunkte

### Chat mit Ollama
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dein-geheimer-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Hallo!"}]
  }'
```

### Shell-Command ausführen
```bash
curl -X POST http://localhost:8000/api/shell/execute \
  -H "Authorization: Bearer dein-geheimer-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "ls", "args": ["-la"]}'
```

### Gmail: Mails auflisten
```bash
curl -http://localhost:8000/api/gmail/mails \
  -H "Authorization: Bearer dein-geheimer-api-key" \
  -G --data-urlencode "max_results=10"
```

### Gmail: Mail lesen
```bash
curl http://localhost:8000/api/gmail/mail/{message_id} \
  -H "Authorization: Bearer dein-geheimer-api-key"
```

### Telegram: Bot starten (Polling)
Der Bot wird automatisch beim Start registriert. Nachrichten an den Bot werden an Ollama weitergeleitet.

## Sicherheit

- HTTP-API durch Bearer-Token geschützt
- Shell-Commands NUR aus expliziter Allowlist erlaubt
- Keine freien Benutzereingaben an Shell
- Gmail-Credentials lokal gespeichert
