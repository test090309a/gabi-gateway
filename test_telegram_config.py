import yaml
from pathlib import Path

config_path = Path("config.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

telegram = config.get("telegram", {})
print(f"telegram.enabled: {telegram.get('enabled')}")
print(f"telegram.bot_token: {telegram.get('bot_token', '')[:15]}...")
print(f"Type of enabled: {type(telegram.get('enabled'))}")

# Prüfe ob enabled als Boolean geladen wird
if telegram.get('enabled') is True:
    print("✅ Telegram is ENABLED")
else:
    print("❌ Telegram is DISABLED")