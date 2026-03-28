# test_web.py
import asyncio
from gateway.integrations.web_automation import get_web_automation

async def test_web():
    print("🌐 Testing WebAutomation...")
    
    web = get_web_automation(headless=True)
    
    result = await web.goto("https://httpbin.org/html")
    print(f"Success: {result.get('success')}")
    print(f"Title: {result.get('title')}")
    print(f"Has screenshot: {'base64' in result.get('screenshot', {})}")
    
    web.close()

if __name__ == "__main__":
    asyncio.run(test_web())