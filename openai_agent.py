import openai
import json
import os
import logging
import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("openai_agent.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("OpenAI_Agent")

class OpenAIAgent:
    def __init__(self):
        # OpenAI API kulcs betöltése fájlból
        try:
            with open('openai_key.txt', 'r') as f:
                api_key = f.read().strip()
                # Az új API verzió környezeti változóként várja a kulcsot
                os.environ["OPENAI_API_KEY"] = api_key
        except FileNotFoundError:
            raise Exception("OpenAI API kulcs fájl (openai_key.txt) nem található!")
        except Exception as e:
            raise Exception(f"Hiba az OpenAI API kulcs betöltésekor: {str(e)}")

    def analyze_and_execute(self, log_text: str, send_command_callback) -> None:
        """
        Elemzi a log szöveget és végrehajtja a javasolt parancsot, ha van.
        
        Args:
            log_text (str): A log szöveg amit elemezni kell
            send_command_callback (callable): Függvény a parancs végrehajtásához
            
        Returns:
            None
        """
        try:
            # Log elemzése a meglévő funkcióval
            analysis_result = self.analyze_server_status(log_text)
            
            # Javaslatok feldolgozása
            for recommendation in analysis_result.get("recommendations", []):
                # Parancs formátum ellenőrzése
                if recommendation.startswith("CMD:") or recommendation.startswith("REPLAY:"):
                    # Parancs végrehajtása a callback segítségével
                    send_command_callback(recommendation)
                    # Csak az első végrehajtható parancsot küldjük el
                    break
                    
        except Exception as e:
            logger.error(f"Hiba az analyze_and_execute során: {str(e)}")
    
    def analyze_server_status(self, log_text: str) -> Dict[str, Any]:
        """
        Szerver állapot logok elemzése OpenAI GPT-4 segítségével.
        
        Args:
            log_text (str): A szerver log szövege
            
        Returns:
            Dict[str, Any]: Az elemzés eredménye, amely tartalmazza:
                - responding_servers: Lista a megfelelően válaszoló szerverekről
                - failing_servers: Lista a hibás szerverekről
                - recommendations: Javaslatok listája a problémák megoldására
                - severity: A probléma súlyossága (low/medium/high/critical)
        """
        try:
            # Prompt összeállítása a GPT-4 számára
            prompt = f"""Elemezd a következő szerver log bejegyzéseket és add vissza JSON formátumban:
            - Mely szerverek válaszolnak megfelelően
            - Mely szerverek nem válaszolnak vagy hibásak
            - Mit kellene tenni a problémák megoldására (használj CMD: vagy REPLAY: prefixet ha konkrét parancsot javasolsz)
            - Milyen súlyos a probléma (low/medium/high/critical)

            Példák a javaslatokra:
            - "CMD: systemctl restart nginx" - szerver újraindítás
            - "CMD: ping server1" - kapcsolat tesztelése
            - "REPLAY:1" - előző parancs megismétlése
            - "Növeld a timeout értéket a konfigurációban" - általános javaslat

            Log:
            {log_text}

            Válaszolj kizárólag JSON formátumban, a következő struktúrában:
            {{
                "responding_servers": ["server1", "server2"],
                "failing_servers": ["server3"],
                "recommendations": ["CMD: restart service", "Check configuration"],
                "severity": "low/medium/high/critical"
            }}
            """

            # GPT-4 API hívás az új API verzióval
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Te egy szerver log elemző AI asszisztens vagy. "
                                                "A feladatod a szerverek állapotának és problémáinak elemzése."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            # JSON válasz feldolgozása
            try:
                result = json.loads(response.choices[0].message.content)
                return result
            except json.JSONDecodeError:
                raise Exception("Hiba: Az AI válasza nem valid JSON formátum!")

        except Exception as e:
            raise Exception(f"OpenAI API hiba: {str(e)}")

    def format_analysis_result(self, result: Dict[str, Any]) -> str:
        """
        Az elemzés eredményének formázása olvasható szöveggé.
        
        Args:
            result (Dict[str, Any]): Az analyze_server_status által visszaadott elemzés
            
        Returns:
            str: Formázott szöveg az eredményekkel
        """
        output = []
        output.append("🔍 Szerver Státusz Elemzés")
        output.append("=" * 30)
        
        output.append("\n✅ Megfelelően válaszoló szerverek:")
        for server in result.get("responding_servers", []):
            output.append(f"  - {server}")
            
        output.append("\n❌ Problémás szerverek:")
        for server in result.get("failing_servers", []):
            output.append(f"  - {server}")
            
        output.append("\n💡 Javaslatok:")
        for rec in result.get("recommendations", []):
            output.append(f"  - {rec}")
            
        severity_map = {
            "low": "⚪ Alacsony",
            "medium": "🟡 Közepes",
            "high": "🟠 Magas",
            "critical": "🔴 Kritikus"
        }
        
        output.append(f"\n⚠️ Probléma súlyossága: {severity_map.get(result.get('severity', 'unknown'), '❓ Ismeretlen')}")
        
        return "\n".join(output)

    def edit_code_file(self, filepath: str, instruction: str) -> str:
        """
        Beolvas egy Python fájlt, GPT-4 segítségével módosítja az instrukció alapján,
        majd elmenti az eredményt _ai.py kiterjesztéssel.
        
        Args:
            filepath (str): A módosítandó Python fájl elérési útja
            instruction (str): Az instrukció a kód módosítására
            
        Returns:
            str: Az új fájl elérési útja
        """
        try:
            # Fájl beolvasása
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # Új fájlnév generálása
            directory, filename = os.path.split(filepath)
            filename_without_ext, _ = os.path.splitext(filename)
            new_filepath = os.path.join(directory, f"{filename_without_ext}_ai.py")
            
            # Prompt összeállítása a GPT-4 számára
            prompt = f"""Ez egy Python fájl tartalma. Kérlek végezd el a következő módosítást: {instruction}. Add vissza az új kódot Python fájl formájában, kommentek nélkül.

            Python fájl tartalma:
            ```python
            {file_content}
            ```
            """

            # GPT-4 API hívás
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Te egy Python kódfejlesztő AI asszisztens vagy. "
                                                 "A feladatod a kapott Python kód módosítása a megadott instrukciók alapján."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            # Csak a kódot mentsük el, a magyarázat nélkül
            ai_response = response.choices[0].message.content
            
            # Kód kinyerése a válaszból (ha code blockban van)
            code_content = ai_response
            if "```python" in ai_response and "```" in ai_response:
                # Kód kinyerése a python code block-ból
                code_blocks = ai_response.split("```")
                for i, block in enumerate(code_blocks):
                    if block.strip().startswith("python") or (i > 0 and code_blocks[i-1].strip().endswith("python")):
                        code_content = block.replace("python", "").strip()
                        break
            
            # Új fájl mentése
            with open(new_filepath, 'w', encoding='utf-8') as f:
                f.write(code_content)
            
            # Esemény naplózása az openai_agent.log fájlba (már konfigurálva van)
            logger.info(f"Kód módosítás végrehajtva: {filepath} -> {new_filepath} | Instrukció: {instruction}")
            
            # Esemény naplózása a copilot_journal.md fájlba
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            journal_entry = f"""
## {timestamp} - Kód Módosítás

- **Eredeti fájl:** `{filepath}`
- **Új fájl:** `{new_filepath}`
- **Instrukció:** {instruction}
- **Státusz:** ✅ Sikeres
            """
            
            # Létrehozzuk vagy hozzáfűzzük a journal fájlt
            with open("copilot_journal.md", "a", encoding='utf-8') as f:
                f.write(journal_entry)
            
            return new_filepath
            
        except Exception as e:
            error_msg = f"Hiba a kód módosítása során: {str(e)}"
            logger.error(error_msg)
            
            # Hiba naplózása a copilot_journal.md fájlba
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            journal_entry = f"""
## {timestamp} - Kód Módosítás

- **Eredeti fájl:** `{filepath}`
- **Instrukció:** {instruction}
- **Státusz:** ❌ Sikertelen
- **Hiba:** {str(e)}
            """
            
            # Létrehozzuk vagy hozzáfűzzük a journal fájlt
            with open("copilot_journal.md", "a", encoding='utf-8') as f:
                f.write(journal_entry)
            
            raise Exception(error_msg)

if __name__ == "__main__":
    # Példa használat
    agent = OpenAIAgent()
    
    test_log = """
    [2025-04-13 10:15:23] Server app1.example.com - Ping response time: 1.5ms
    [2025-04-13 10:15:24] Server db1.example.com - Connection timeout after 30s
    [2025-04-13 10:15:25] Server app2.example.com - SSH connection refused
    [2025-04-13 10:15:26] Server cache1.example.com - Response: 200 OK
    """
    
    try:
        result = agent.analyze_server_status(test_log)
        print(agent.format_analysis_result(result))
    except Exception as e:
        print(f"Hiba: {str(e)}")