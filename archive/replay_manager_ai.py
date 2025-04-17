import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("replay_manager.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Replay_Manager")

class ReplayManager:
    
    def __init__(self, max_history_size: int = 10, max_retries: int = 3, retry_cooldown: float = 1.0):
        self.max_history_size = max_history_size
        self.max_retries = max_retries
        self.retry_cooldown = retry_cooldown
        
        self.command_history: List[Dict[str, Any]] = []
        self.failed_commands: Dict[str, int] = {}
        self.last_execution: Dict[str, float] = {}

    def log_to_journal(self, action, message, success=True):
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅" if success else "❌"
        
        log_entry = f"\n## {action} {status}\n"
        log_entry += f"**Time**: {timestamp}\n"
        log_entry += f"**Details**: {message}\n"
        
        with open('copilot_journal.md', 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def add_command(self, command: str, response: str, success: bool = True) -> None:
        timestamp = datetime.now().isoformat()
        
        entry = {
            "timestamp": timestamp,
            "command": command,
            "response": response,
            "success": success
        }
        
        self.command_history.insert(0, entry)
        if len(self.command_history) > self.max_history_size:
            self.command_history.pop()
        
        self.last_execution[command] = time.time()
        
        if not success:
            self.failed_commands[command] = self.failed_commands.get(command, 0) + 1
        else:
            self.failed_commands.pop(command, None)
        
        logger.info(f"Command added to history: {command[:50]}...")
        
        self.log_to_journal(command, response, success)
    
    def get_command(self, index: int) -> Optional[Dict[str, Any]]:
        try:
            actual_index = index - 1
            if 0 <= actual_index < len(self.command_history):
                return self.command_history[actual_index]
            return None
        except Exception as e:
            logger.error(f"Error getting command: {e}")
            return None
    
    def should_retry(self, command: str) -> bool:
        current_attempts = self.failed_commands.get(command, 0)
        if current_attempts >= self.max_retries:
            logger.warning(f"Max retries reached for command: {command}")
            return False
        
        if command in self.last_execution:
            last_execution = self.last_execution[command]
            if time.time() - last_execution < self.retry_cooldown:
                logger.info(f"Command {command} in cooldown")
                return False
        
        return True
    
    def clear_history(self) -> None:
        self.command_history.clear()
        self.failed_commands.clear()
        self.last_execution.clear()
        logger.info("Command history cleared")

    def remove_failed_only(self) -> None:
        self.failed_commands.clear()
        logger.info("Failed commands cleared")
    
    def validate_command(self, command: str) -> bool:
        if not command or not isinstance(command, str):
            return False
        
        valid_prefixes = ("CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:")
        if not command.startswith(valid_prefixes):
            return False
        
        if command.startswith("REPLAY:"):
            try:
                index = int(command.split(":")[1].strip())
                if index < 1 or index > len(self.command_history):
                    return False
            except (ValueError, IndexError):
                return False
        
        return True
    
    def get_retry_status(self, command: str) -> Dict[str, Any]:
        return {
            "attempts": self.failed_commands.get(command, 0),
            "max_retries": self.max_retries,
            "can_retry": self.should_retry(command),
            "cooldown": max(0, self.retry_cooldown - 
                          (time.time() - self.last_execution.get(command, 0)))
        }
    
    def export_history(self, file_path: str) -> None:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.command_history, f, indent=2)
            logger.info(f"Command history exported to {file_path}")
        except Exception as e:
            logger.error(f"Error exporting history: {e}")
    
    def import_history(self, file_path: str) -> None:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
                
            if isinstance(history, list):
                self.command_history = history[:self.max_history_size]
                logger.info(f"Command history imported from {file_path}")
            else:
                raise ValueError("Invalid history file format")
        except Exception as e:
            logger.error(f"Error importing history: {e}")

    async def replay_command(self, command_id: int) -> str:
        try:
            command = self._get_command_by_id(command_id)
            if not command:
                return f"Nem található {command_id} azonosítójú parancs a naplóban"
            
            from command_server import CommandServer
            server = CommandServer()
            
            if command.startswith("CMD:"):
                result = await server.execute_command(command)
            elif command.startswith("CODE:"):
                result = await server.execute_code(command)
            else:
                return f"Nem támogatott parancstípus: {command}"
            
            self.add_command(command, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Hiba a parancs újrajátszásakor: {e}")
            return f"Hiba a parancs újrajátszásakor: {e}"
    
    def _get_command_by_id(self, command_id: int) -> str:
        try:
            with open("command_log.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            command_count = 0
            for i in range(0, len(lines), 3):  
                if i + 1 >= len(lines):
                    break
                    
                line = lines[i].strip()
                if line.startswith("[") and "COMMAND:" in line:
                    command_count += 1
                    if command_count == command_id:
                        command = line.split("COMMAND:", 1)[1].strip()
                        return command
                        
            return None
            
        except Exception as e:
            logger.error(f"Hiba a parancs kiolvasásakor: {e}")
            return None

    async def start_retry_loop(self) -> None:
        import asyncio
        
        logger.info("Starting retry loop for failed commands")
        self.log_to_journal(
            "SYSTEM: Retry Loop Started",
            "Automatic retry loop for failed commands has been initiated",
            True
        )
        
        while True:
            try:
                for command, attempts in list(self.failed_commands.items()):
                    if self.should_retry(command):
                        for i, entry in enumerate(self.command_history):
                            if entry["command"] == command:
                                logger.info(f"Retrying failed command: {command[:50]}...")
                                
                                self.log_to_journal(
                                    f"RETRY: {command}",
                                    f"Automatic retry attempt #{attempts + 1}",
                                    True
                                )
                                
                                await self.replay_command(i + 1)  
                                break
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in retry loop: {e}")
                self.log_to_journal(
                    "SYSTEM: Retry Loop Error",
                    f"Error occurred in automatic retry loop: {str(e)}",
                    False
                )
                await asyncio.sleep(10)

    async def handle_failed_command(self, command_id: int) -> None:
        try:
            command = self._get_command_by_id(command_id)
            if not command:
                logger.error(f"Command with id {command_id} not found in history")
                return

            if self.should_retry(command):
                logger.info(f"Retrying failed command: {command[:50]}...")
                result = await self.replay_command(command_id)
                if result:
                    logger.info(f"Command {command[:50]}... retried successfully")
                    self.log_to_journal(f"RETRY: {command}", "Command retried successfully", True)
                else:
                    logger.error(f"Command {command[:50]}... failed after retry")
                    self.log_to_journal(f"RETRY: {command}", "Command failed after retry", False)
            else:
                logger.warning(f"Command {command[:50]}... cannot be retried")
        except Exception as e:
            logger.error(f"Error handling failed command: {e}")