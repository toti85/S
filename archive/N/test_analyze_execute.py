from openai_agent import OpenAIAgent

def test_command_callback(command):
    """Teszt callback függvény a parancsok fogadására"""
    print(f"\nParancs végrehajtása: {command}")

# Teszt log létrehozása hibás szerverrel
test_log = """
[2025-04-14 15:00:01] Server web01.local - HTTP Status: 200 OK
[2025-04-14 15:00:02] Server db01.local - Connection timeout after 30s
[2025-04-14 15:00:03] Server db01.local - Retry attempt 1 failed
[2025-04-14 15:00:04] Server db01.local - Service unreachable
"""

def main():
    print("OpenAI Agent Analyze & Execute Teszt")
    print("-" * 40)
    
    try:
        # Agent példányosítása
        agent = OpenAIAgent()
        
        # Log elemzése és végrehajtás
        print("Log elemzése és parancs végrehajtása...")
        agent.analyze_and_execute(test_log, test_command_callback)
        
    except Exception as e:
        print(f"\n❌ Hiba történt: {str(e)}")
        
    print("\nTeszt befejezve.")

if __name__ == "__main__":
    main()