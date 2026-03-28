# test_som.py
import asyncio
from gateway.integrations.som_agent import SoMAgent

async def test_som():
    print("🔍 Testing SoM Agent with Startpage...")
    
    agent = SoMAgent(headless=True)
    
    result = await agent.navigate(
        url="https://www.startpage.com",
        goal="Suche nach wetter in wien",
        max_steps=5
    )
    
    print(f"\n📊 Result:")
    print(f"  Success: {result.get('success')}")
    print(f"  Error: {result.get('error', 'None')}")
    
    if result.get("success"):
        extracted = result.get("extracted_content", {})
        print(f"  Title: {extracted.get('title', 'No title')}")
        print(f"  Text length: {len(extracted.get('text', ''))}")
        
        search_results = extracted.get("search_results", [])
        print(f"  Found {len(search_results)} search results")
        
        if search_results:
            print("\n📋 First 3 results:")
            for i, res in enumerate(search_results[:3], 1):
                print(f"  {i}. Title: {res.get('title', 'No title')[:60]}")
                print(f"     URL: {res.get('url', '')[:80]}")
        else:
            # Zeige den HTML-Code der Seite für Debugging
            html = extracted.get('html', '')[:500]
            if html:
                print("\n📄 HTML Preview:")
                print(html)
    else:
        print(f"  Error details: {result.get('error')}")
    
    agent.close()

if __name__ == "__main__":
    asyncio.run(test_som())