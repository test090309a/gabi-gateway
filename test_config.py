# test_config_simple.py
import yaml
from pathlib import Path

config_path = Path("config.yaml")
print(f"Config path: {config_path.absolute()}")
print(f"Config exists: {config_path.exists()}")

if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    print("\n=== Telegram Config ===")
    telegram = config_data.get("telegram", {})
    print(f"telegram.enabled: {telegram.get('enabled', False)}")
    print(f"telegram.bot_token: {telegram.get('bot_token', '')[:15]}...")
    print(f"telegram.chat_id: {telegram.get('chat_id')}")
    print(f"telegram.channel_id: {telegram.get('channel_id')}")
    
    print("\n=== Full telegram section ===")
    print(telegram)
else:
    print("❌ config.yaml not found!")