import asyncio
import logging
from ai_command_handler import AICommandHandler
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_handler.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Test_Handler")

class TestCommandHandler:
    def __init__(self):
        # Konfiguráció
        self.chrome_path = r"C:\S\chatgpt_selenium_automation\chrome-win64\chrome.exe"
        self.chrome_driver_path = r"C:\S\chatgpt_selenium_automation\chromedriver-win64\chromedriver.exe"
        self.handler = AICommandHandler(self.chrome_path, self.chrome_driver_path)
        
    async def test_command_execution(self):
        """Parancs végrehajtás tesztelése"""
        logger.info("\n=== Parancs Végrehajtás Teszt ===")
        
        # Teszt parancs
        command = "CMD: echo Hello World"
        response = await self.handler.send_command_to_websocket(command)
        logger.info(f"Parancs: {command}")
        logger.info(f"Válasz: {response}")
        
        return "Hello World" in response
        
    async def test_error_handling(self):
        """Hibakezelés tesztelése"""
        logger.info("\n=== Hibakezelés Teszt ===")
        
        # Hibás parancs
        command = "CMD: invalid_command_test"
        response = await self.handler.send_command_to_websocket(command)
        logger.info(f"Hibás parancs: {command}")
        logger.info(f"Válasz: {response}")
        
        # Ellenőrizzük, hogy a parancs bekerült-e a failed_commands-ba
        is_tracked = command in self.handler.failed_commands
        count = self.handler.failed_commands.get(command, 0)
        
        logger.info(f"Követett hiba: {is_tracked}")
        logger.info(f"Hibaszámláló: {count}")
        
        return is_tracked and count > 0
        
    async def test_replay_functionality(self):
        """REPLAY funkció tesztelése"""
        logger.info("\n=== REPLAY Funkció Teszt ===")
        
        # Első parancs végrehajtása
        original_command = "CMD: echo Test Replay"
        response1 = await self.handler.send_command_to_websocket(original_command)
        logger.info(f"Eredeti parancs: {original_command}")
        logger.info(f"Válasz 1: {response1}")
        
        # REPLAY parancs generálás
        if original_command in self.handler.command_history:
            index = self.handler.command_history.index(original_command) + 1
            replay_command = f"REPLAY:{index}"
            
            response2 = await self.handler.send_command_to_websocket(replay_command)
            logger.info(f"REPLAY parancs: {replay_command}")
            logger.info(f"Válasz 2: {response2}")
            
            return response1 == response2
        
        return False
        
    async def test_automatic_retry(self):
        """Automatikus újrapróbálkozás tesztelése"""
        logger.info("\n=== Automatikus Újrapróbálkozás Teszt ===")
        
        # Hibás parancs ami újrapróbálkozást vált ki
        command = "CMD: dir /invalid_flag"
        response = await self.handler.send_command_to_websocket(command)
        
        # Ellenőrizzük a hibaszámlálót és a REPLAY próbálkozásokat
        retry_count = self.handler.failed_commands.get(command, 0)
        logger.info(f"Hibás parancs: {command}")
        logger.info(f"Újrapróbálkozások száma: {retry_count}")
        logger.info(f"Válasz: {response}")
        
        return retry_count > 0 and retry_count <= self.handler.max_retries
        
    async def test_command_history(self):
        """Command history működésének tesztelése"""
        logger.info("\n=== Command History Teszt ===")
        
        # Több parancs végrehajtása
        commands = [
            "CMD: echo First",
            "CMD: echo Second",
            "CMD: echo Third"
        ]
        
        for cmd in commands:
            await self.handler.send_command_to_websocket(cmd)
            
        # Ellenőrizzük a history tartalmát
        history_size = len(self.handler.command_history)
        last_command = self.handler.command_history[0] if history_size > 0 else None
        
        logger.info(f"History méret: {history_size}")
        logger.info(f"Utolsó parancs: {last_command}")
        
        return history_size > 0 and last_command == commands[-1]
        
    async def run_all_tests(self):
        """Összes teszt futtatása"""
        test_results = {
            "command_execution": False,
            "error_handling": False,
            "replay_functionality": False,
            "automatic_retry": False,
            "command_history": False
        }
        
        try:
            # Tesztek futtatása
            test_results["command_execution"] = await self.test_command_execution()
            test_results["error_handling"] = await self.test_error_handling()
            test_results["replay_functionality"] = await self.test_replay_functionality()
            test_results["automatic_retry"] = await self.test_automatic_retry()
            test_results["command_history"] = await self.test_command_history()
            
            # Eredmények kiírása
            logger.info("\n=== Teszt Eredmények ===")
            for test_name, result in test_results.items():
                status = "✅ SIKERES" if result else "❌ SIKERTELEN"
                logger.info(f"{test_name}: {status}")
                
        except Exception as e:
            logger.error(f"Hiba a tesztek futtatása közben: {str(e)}")
            
        finally:
            # Cleanup
            try:
                self.handler.close()
            except:
                pass
            
        return test_results

def main():
    # Tesztek futtatása
    tester = TestCommandHandler()
    print("\n🔍 AI Command Handler Rendszer Teszt")
    print("=" * 40)
    
    try:
        asyncio.run(tester.run_all_tests())
    except KeyboardInterrupt:
        print("\n\nTesztek megszakítva felhasználó által.")
    except Exception as e:
        print(f"\n\n❌ Hiba történt: {str(e)}")
    finally:
        print("\n✨ Tesztek befejezve.")

if __name__ == "__main__":
    main()