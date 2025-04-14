import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
import json

# Configure logging
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
    """
    Manages command history and replay functionality.
    Handles automatic retries and command validation.
    """
    
    def __init__(self, max_history_size: int = 10, max_retries: int = 3, retry_cooldown: float = 1.0):
        self.max_history_size = max_history_size
        self.max_retries = max_retries
        self.retry_cooldown = retry_cooldown
        
        self.command_history: List[Dict[str, Any]] = []
        self.failed_commands: Dict[str, int] = {}
        self.last_execution: Dict[str, float] = {}
    
    def add_command(self, command: str, response: str, success: bool = True) -> None:
        """
        Add a command and its response to history.
        
        Args:
            command: The executed command
            response: The command's response
            success: Whether the command executed successfully
        """
        timestamp = datetime.now().isoformat()
        
        # Create command entry
        entry = {
            "timestamp": timestamp,
            "command": command,
            "response": response,
            "success": success
        }
        
        # Add to history and maintain size limit
        self.command_history.insert(0, entry)
        if len(self.command_history) > self.max_history_size:
            self.command_history.pop()
        
        # Update execution tracking
        self.last_execution[command] = time.time()
        
        # Update failed commands tracking
        if not success:
            self.failed_commands[command] = self.failed_commands.get(command, 0) + 1
        else:
            # Clear failed attempts on success
            self.failed_commands.pop(command, None)
        
        logger.info(f"Command added to history: {command[:50]}...")
    
    def get_command(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Get a command entry by its index (1-based).
        
        Args:
            index: The 1-based index of the command to retrieve
            
        Returns:
            The command entry or None if not found
        """
        try:
            # Convert to 0-based index
            actual_index = index - 1
            if 0 <= actual_index < len(self.command_history):
                return self.command_history[actual_index]
            return None
        except Exception as e:
            logger.error(f"Error getting command: {e}")
            return None
    
    def should_retry(self, command: str) -> bool:
        """
        Check if a failed command should be retried.
        
        Args:
            command: The command to check
            
        Returns:
            True if the command should be retried, False otherwise
        """
        # Check retry count
        if self.failed_commands.get(command, 0) >= self.max_retries:
            logger.warning(f"Max retries reached for command: {command}")
            return False
        
        # Check cooldown only if there was a previous execution
        if command in self.last_execution:
            last_execution = self.last_execution[command]
            if time.time() - last_execution < self.retry_cooldown:
                logger.info(f"Command {command} in cooldown")
                return False
        
        return True
    
    def clear_history(self) -> None:
        """Clear command history and tracking data"""
        self.command_history.clear()
        self.failed_commands.clear()
        self.last_execution.clear()
        logger.info("Command history cleared")
    
    def validate_command(self, command: str) -> bool:
        """
        Validate a command before execution.
        
        Args:
            command: The command to validate
            
        Returns:
            True if command is valid, False otherwise
        """
        if not command or not isinstance(command, str):
            return False
        
        # Check for valid command prefixes
        valid_prefixes = ("CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:")
        if not command.startswith(valid_prefixes):
            return False
        
        # Special validation for REPLAY commands
        if command.startswith("REPLAY:"):
            try:
                index = int(command.split(":")[1].strip())
                if index < 1 or index > len(self.command_history):
                    return False
            except (ValueError, IndexError):
                return False
        
        return True
    
    def get_retry_status(self, command: str) -> Dict[str, Any]:
        """
        Get retry status information for a command.
        
        Args:
            command: The command to check
            
        Returns:
            Dict with retry status information
        """
        return {
            "attempts": self.failed_commands.get(command, 0),
            "max_retries": self.max_retries,
            "can_retry": self.should_retry(command),
            "cooldown": max(0, self.retry_cooldown - 
                          (time.time() - self.last_execution.get(command, 0)))
        }
    
    def export_history(self, file_path: str) -> None:
        """
        Export command history to a JSON file.
        
        Args:
            file_path: Path to save the history file
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.command_history, f, indent=2)
            logger.info(f"Command history exported to {file_path}")
        except Exception as e:
            logger.error(f"Error exporting history: {e}")
    
    def import_history(self, file_path: str) -> None:
        """
        Import command history from a JSON file.
        
        Args:
            file_path: Path to the history file to import
        """
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