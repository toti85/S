from openai_agent import OpenAIAgent

agent = OpenAIAgent()
new_file_path = agent.edit_code_file(
    "replay_manager.py",
    "Adj hozzá egy metódust 'remove_failed_only' néven, amely csak a sikertelen parancsokat törli (failed_commands dictionary)"
)

print(f"Módosított fájl elérési útja: {new_file_path}")
