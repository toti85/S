from openai_agent import OpenAIAgent

# Teszt log létrehozása
test_log = """
[2025-04-14 10:00:01] Server web01.local - HTTP Status: 200 OK, Response time: 150ms
[2025-04-14 10:00:02] Server db01.local - Connection timeout after 30s
[2025-04-14 10:00:03] Server cache01.local - Memory usage: 95%, CPU: 88%
[2025-04-14 10:00:04] Server web02.local - HTTP Status: 200 OK, Response time: 180ms
[2025-04-14 10:00:05] Server db01.local - Retry attempt 1 failed: Connection refused
"""

def test_agent():
    print("OpenAI Agent Teszt Kezdődik...")
    print("-" * 50)
    
    try:
        # Agent példányosítása
        agent = OpenAIAgent()
        
        # Log elemzése
        print("Log elemzése folyamatban...")
        result = agent.analyze_server_status(test_log)
        
        # Eredmény formázott megjelenítése
        print("\nElemzés eredménye:")
        print(agent.format_analysis_result(result))
        
    except Exception as e:
        print(f"\n❌ Hiba történt: {str(e)}")
        
    print("\nTeszt befejezve.")

if __name__ == "__main__":
    test_agent()