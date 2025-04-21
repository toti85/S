import asyncio
import websockets
import subprocess
import platform
import os
import json
import logging
from datetime import datetime
from io import StringIO
import sys
from core.command_library import COMMAND_LIBRARY  # Importáljuk a parancskönyvtárat

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("command_server.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Command_Server")

class CommandServer:
    """
    WebSocket server that processes commands from the AI Command Handler.
    Handles different command types and returns responses.
    """
    
    # Static variables for command history
    _command_history = []  # Store command history for replay
    _max_history_size = 10  # Maximum history size
    
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.code_filename = "generated_code.py"
        self.last_command = None  # Store last command for retry
        self.retry_in_progress = False  # Flag to prevent infinite retries

    @classmethod
    def add_to_history(cls, command):
        """Add command to history if not already present"""
        if not command.startswith("REPLAY:"):
            if command not in cls._command_history:
                cls._command_history.insert(0, command)
                if len(cls._command_history) > cls._max_history_size:
                    cls._command_history.pop()
            logger.info(f"Command added to history: {command[:50]}...")

    @classmethod
    def get_from_history(cls, index):
        """Get command from history by index"""
        if 0 <= index < len(cls._command_history):
            return cls._command_history[index]
        return None
    
    async def handle_cmd(self, cmd):
        """Execute a shell command and return the output"""
        logger.info(f"Executing CMD: {cmd}")
        try:
            # Ellenőrizzük, hogy JSON formátumú parancs-e
            if cmd.strip().startswith("{") and cmd.strip().endswith("}"):
                try:
                    cmd_json = json.loads(cmd)
                    if "parancs" in cmd_json:
                        command_name = cmd_json["parancs"].lower().strip()
                        command_args = cmd_json.get("paraméterek", "").strip()
                        
                        logger.info(f"JSON parancs feldolgozása: {command_name} paraméterekkel: {command_args}")
                        
                        # Ellenőrizzük, hogy a parancs megtalálható-e a parancskönyvtárban
                        if command_name in COMMAND_LIBRARY:
                            try:
                                result = COMMAND_LIBRARY[command_name](command_args)
                                self.add_to_history(f"CMD: {command_name} {command_args}")
                                return result
                            except Exception as e:
                                return f"Hiba a parancskönyvtári parancs végrehajtásakor: {str(e)}"
                        else:
                            return f"Ismeretlen parancs a parancskönyvtárban: {command_name}"
                except json.JSONDecodeError:
                    logger.error("Hibás JSON formátum a parancsban")
                    return "Hibás JSON formátum a parancsban"
            
            # Speciális "diagnose network" parancs kezelése
            if cmd.strip().lower() == "diagnose network":
                logger.info("Hálózati diagnosztika indítása")
                try:
                    # Importáljuk és futtassuk a network_diagnostics modult
                    from core.network_diagnostics import diagnose_network
                    
                    # Definiáljuk a célpontokat
                    targets = [
                        "192.168.0.1",      # Router
                        "192.168.0.50",     # NAS
                        "192.168.0.10",     # PC
                        "8.8.8.8",          # Google DNS
                        "1.1.1.1"           # Cloudflare DNS
                    ]
                    
                    # Futtassuk a diagnosztikát, hogy visszakapjuk az eredményt
                    results = diagnose_network(targets)
                    
                    # Biztosítsuk, hogy a logs könyvtár létezik
                    import os
                    if not os.path.exists("logs"):
                        os.makedirs("logs")
                        
                    # Mentsük el a diagnosztika eredményét
                    with open("logs/network_diagnostics.json", "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=4, ensure_ascii=False)
                    
                    # Formázzuk a JSON-t egy egysoros, idézhető formátumra
                    # Használjuk az egyszerű JSON formátumot a könnyebb kezeléshez
                    simple_json = json.dumps({
                        "status": "teszt",
                        "tipus": "json",
                        "komponens": "response_router",
                        "timestamp": results["timestamp"],
                        "targets_count": len(results["results"]),
                        "results": results["results"]
                    }, ensure_ascii=False)
                    
                    logger.info(f"Diagnosztika eredmény JSON létrehozva: {simple_json[:100]}...")
                    return simple_json
                    
                except ImportError:
                    return "Hiba: A network_diagnostics modul nem található."
                except Exception as e:
                    logger.error(f"Hiba a hálózati diagnosztika futtatásakor: {e}")
                    return f"Hiba a hálózati diagnosztika futtatásakor: {str(e)}"
                    
            # Ellenőrizzük, hogy a parancs elérhető-e a parancskönyvtárban
            cmd_parts = cmd.strip().split(None, 1)
            base_cmd = cmd_parts[0].lower() if cmd_parts else ""
            args = cmd_parts[1] if len(cmd_parts) > 1 else ""
            
            if base_cmd in COMMAND_LIBRARY:
                try:
                    logger.info(f"Parancskönyvtári parancs végrehajtása: {base_cmd}")
                    result = COMMAND_LIBRARY[base_cmd](args)
                    self.add_to_history(f"CMD: {cmd}")
                    return result
                except Exception as e:
                    logger.error(f"Hiba a parancskönyvtári parancs végrehajtásakor: {e}")
                    return f"Hiba a parancs végrehajtásakor: {str(e)}"
            
            # Ha nincs a parancskönyvtárban, akkor végrehajtjuk közvetlenül
            # Set UTF-8 encoding for subprocess
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=env,
                timeout=60
            )
            
            # Check for command failure
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Command failed with no output"
                logger.error(f"Command failed with return code {result.returncode}: {error_msg}")
                
                # Retry handling
                if not self.retry_in_progress and self.last_command != cmd:
                    logger.info("parancshiba - automatikus újrapróbálás következik")
                    self.last_command = cmd
                    self.retry_in_progress = True
                    return "RETRY_NEEDED"  # Special flag for retry
                else:
                    # Reset retry flag and return error
                    self.retry_in_progress = False
                    return f"Error executing command: {error_msg}"
            
            # Reset retry state on success
            self.retry_in_progress = False
            output = result.stdout or result.stderr
            
            # Add successful command to history
            if output:
                self.add_to_history(f"CMD: {cmd}")
                
            return output or "Command executed (no output)"
            
        except subprocess.TimeoutExpired:
            self.retry_in_progress = False
            return "Command timed out after 60 seconds"
        except Exception as e:
            self.retry_in_progress = False
            logger.error(f"Error executing command: {e}")
            return f"Error executing command: {e}"
    
    async def handle_code(self, code):
        """Write code to file and execute it, returning the output"""
        logger.info("Executing CODE block")
        try:
            # Save code to file with UTF-8 encoding and BOM
            with open(self.code_filename, "w", encoding="utf-8-sig") as f:
                f.write("#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n")
                f.write("import sys\n")
                f.write("sys.stdout.reconfigure(encoding='utf-8')\n")
                f.write("sys.stderr.reconfigure(encoding='utf-8')\n")
                f.write(code)
            
            # Execute the code with explicit UTF-8 encoding
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
            
            result = subprocess.run(
                ["python", "-X", "utf8", self.code_filename],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                timeout=60
            )
            
            # Check for code execution failure
            if result.returncode != 0:
                error_msg = f"Error:\n{result.stderr}\n\nOutput:\n{result.stdout}"
                logger.error(f"Code execution failed with return code {result.returncode}")
                
                # If not already retrying, store code and trigger retry
                if not self.retry_in_progress and self.last_command != code:
                    logger.info("parancshiba - automatikus újrapróbálás következik")
                    self.last_command = code
                    self.retry_in_progress = True
                    return "RETRY_NEEDED"
                else:
                    # Reset retry flag and return error
                    self.retry_in_progress = False
                    return error_msg
            
            # Reset retry state on success
            self.retry_in_progress = False
            return result.stdout or "Code executed (no output)"
            
        except subprocess.TimeoutExpired:
            self.retry_in_progress = False
            return "Code execution timed out after 60 seconds"
        except Exception as e:
            self.retry_in_progress = False
            logger.error(f"Error executing code: {e}")
            return f"Error executing code: {e}"
    
    async def handle_info(self):
        """Return system information"""
        logger.info("Retrieving system information")
        try:
            info = {
                "OS": platform.system(),
                "OS_Version": platform.version(),
                "OS_Release": platform.release(),
                "Python": platform.python_version(),
                "Processor": platform.processor(),
                "Machine": platform.machine(),
                "Node": platform.node(),
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return json.dumps(info, indent=2)
        except Exception as e:
            logger.error(f"Error retrieving system info: {e}")
            return f"Error retrieving system info: {e}"
    
    async def handle_file(self, params):
        """Handle file operations (read/write)"""
        logger.info(f"Processing FILE operation: {params[:50]}...")
        try:
            # Extract operation type (read or write)
            if params.startswith("read "):
                # Read file operation
                filepath = params[5:].strip()
                logger.info(f"Reading file: {filepath}")
                
                # Security check - prevent directory traversal
                if ".." in filepath or "~" in filepath:
                    return "Security error: Invalid file path"
                
                # Read file content
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Truncate if too large
                    if len(content) > 5000:
                        content = content[:5000] + "\n...(truncated)..."
                    
                    return f"File content of {filepath}:\n\n{content}"
                except FileNotFoundError:
                    return f"Error: File not found: {filepath}"
                except Exception as e:
                    return f"Error reading file: {e}"
                
            elif params.startswith("write "):
                # Write file operation
                params = params[6:]
                
                # Split by || delimiter between path and content
                if "||" in params:
                    filepath, content = params.split("||", 1)
                    filepath = filepath.strip()
                    content = content.strip()
                    
                    # Security check
                    if ".." in filepath or "~" in filepath:
                        return "Security error: Invalid file path"
                    
                    logger.info(f"Writing to file: {filepath}")
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                    # Write content to file
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    return f"Successfully wrote {len(content)} bytes to {filepath}"
                else:
                    return "Error: Invalid FILE:write format. Use 'FILE:write path/to/file || content'"
                
            elif params.startswith("list "):
                # List directory contents
                directory = params[5:].strip()
                
                # Security check
                if ".." in directory or "~" in directory:
                    return "Security error: Invalid directory path"
                
                if not os.path.exists(directory):
                    return f"Error: Directory not found: {directory}"
                
                if not os.path.isdir(directory):
                    return f"Error: Not a directory: {directory}"
                
                # List directory contents
                files = os.listdir(directory)
                result = f"Contents of {directory}:\n"
                
                for f in files:
                    full_path = os.path.join(directory, f)
                    if os.path.isdir(full_path):
                        f += "/"
                    result += f"- {f}\n"
                
                return result
            else:
                return f"Unsupported FILE operation: {params}"
                
        except Exception as e:
            logger.error(f"Error in FILE operation: {e}")
            return f"Error in FILE operation: {e}"
    
    async def command_handler(self, websocket):
        """Handles incoming WebSocket connections and commands"""
        client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"New connection from {client_info}")
        
        try:
            async for message in websocket:
                logger.info(f"Received message from {client_info}: {message[:50]}...")
                
                response = "Unknown command format"
                retry_count = 0
                
                while (retry_count < 2):  # Maximum 1 retry (original + 1 retry)
                    # Process different command types
                    if message.startswith("CMD:"):
                        cmd = message[4:].strip()
                        response = await self.handle_cmd(cmd)
                        # Add successful command to history
                        if response != "RETRY_NEEDED":
                            self.add_to_history(message)
                        
                    elif message.startswith("CODE:"):
                        code = message[5:].strip()
                        response = await self.handle_code(code)
                        # Add successful command to history
                        if response != "RETRY_NEEDED":
                            self.add_to_history(message)
                        
                    elif message.startswith("INFO:"):
                        response = await self.handle_info()
                        self.add_to_history(message)
                        
                    elif message.startswith("FILE:"):
                        params = message[5:].strip()
                        response = await self.handle_file(params)
                        # Add successful command to history
                        if response != "RETRY_NEEDED":
                            self.add_to_history(message)
                    
                    elif message.startswith("REPLAY:"):
                        try:
                            # Get command index from history (1-based)
                            index = int(message[7:].strip()) - 1
                            
                            # Check if index is valid
                            if 0 <= index < len(self._command_history):
                                # Get original command
                                original_command = self.get_from_history(index)
                                logger.info(f"Replaying command: {original_command}")
                                
                                # Execute original command based on its type
                                if original_command.startswith("CMD:"):
                                    response = await self.handle_cmd(original_command[4:].strip())
                                elif original_command.startswith("CODE:"):
                                    response = await self.handle_code(original_command[5:].strip())
                                elif original_command.startswith("FILE:"):
                                    response = await self.handle_file(original_command[5:].strip())
                                elif original_command.startswith("INFO:"):
                                    response = await self.handle_info()
                            else:
                                response = f"Invalid REPLAY index: {index + 1}. History size: {len(self._command_history)}"
                                logger.error(response)
                        except ValueError:
                            response = f"Invalid REPLAY format. Expected number, got: {message[7:]}"
                            logger.error(response)
                        except Exception as e:
                            response = f"Error executing REPLAY: {str(e)}"
                            logger.error(response)
                    
                    # Check if retry is needed
                    if response == "RETRY_NEEDED" and retry_count == 0:
                        logger.info("replay_triggered - Attempting automatic retry")
                        retry_count += 1
                        continue
                    
                    break
                
                # Send final response back to client
                await websocket.send(response)
                logger.info(f"Sent response to {client_info}: {response[:50]}...")
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed with {client_info}")
        except Exception as e:
            logger.error(f"Error handling connection from {client_info}: {e}")
    
    async def start_server(self):
        """Start the WebSocket server"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
                
                # Try to start the server
                async with websockets.serve(self.command_handler, self.host, self.port):
                    logger.info("Server started. Press Ctrl+C to stop.")
                    await asyncio.Future()  # Run forever
                    
            except OSError as e:
                if e.errno == 10048:  # Port already in use
                    if attempt < max_retries - 1:
                        logger.warning(f"Port {self.port} is in use, waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        # Try to find and use an alternative port
                        alternative_port = self.find_free_port()
                        if alternative_port:
                            logger.info(f"Using alternative port: {alternative_port}")
                            self.port = alternative_port
                            async with websockets.serve(self.command_handler, self.host, self.port):
                                logger.info("Server started on alternative port. Press Ctrl+C to stop.")
                                await asyncio.Future()
                        else:
                            logger.error("Could not find a free port to bind to")
                            raise
                else:
                    logger.error(f"Server error: {e}")
                    raise
            except Exception as e:
                logger.error(f"Server error: {e}")
                raise
                
    def find_free_port(self):
        """Find a free port to bind to"""
        import socket
        
        for port in range(8765, 8775):  # Try ports 8765-8774
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except:
                continue
        return None

    async def execute_code(self, code):
        """Execute Python code and return the output"""
        try:
            # Clean up the code content
            code = code.replace("CODE:", "").strip()
            
            # Remove common formatting artifacts
            code = code.replace("python", "").replace("Copy", "").replace("Edit", "").strip()
            if code.startswith("```") and code.endswith("```"):
                code = code[3:-3].strip()
            
            # Save code to temporary file
            with open("generated_code.py", "w", encoding="utf-8") as f:
                f.write(code)
            
            # Create string buffer for output
            output = StringIO()
            sys.stdout = output
            
            try:
                # Execute the code
                exec(code, globals(), locals())
                result = output.getvalue()
                return result if result else "Code executed (no output)"
            except Exception as e:
                return f"Error:\n{str(e)}"
            finally:
                # Restore stdout
                sys.stdout = sys.__stdout__
                
        except Exception as e:
            return f"Error executing code: {str(e)}"
            
    async def execute_command(self, command):
        """Execute a shell command and return the output"""
        try:
            # Clean up command
            command = command.replace("CMD:", "").strip()
            
            # Remove common artifacts
            command = command.replace("Search", "").replace("Deep research", "").strip()
            
            if not command:
                return "Command executed (no output)"
            
            # Execute command and capture output
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if stdout:
                return stdout.decode()
            if stderr:
                return stderr.decode()
            return "Command executed (no output)"
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

def main():
    server = CommandServer()
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    main()