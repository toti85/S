from openai_agent import OpenAIAgent

agent = OpenAIAgent()
new_file_path = agent.edit_code_file(
    "replay_manager.py",
    "Adj hozzá egy metódust remove_failed_only néven, amely csak a failed_commands szótárat törli, a history-t nem"
)
print(f"✅ Új fájl elmentve: {new_file_path}")
