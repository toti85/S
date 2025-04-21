import os
import socket
import threading
import time
import asyncio
import websockets
import logging
import subprocess
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from replay.replay_manager import ReplayManager  # Helyesbített import útvonal
from openai import OpenAI  # Add OpenAI import
import pathlib  # For path handling
import json  # For config handling
import re  # For regex handling
import hashlib  # For caching
import pickle  # For cache serialization
from core.response_router import route_response
from core.command_library import COMMAND_LIBRARY  # Importáljuk a parancskönyvtárat

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ai_command_handler.log", encoding='utf-8'),  # Add UTF-8 encoding here
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("AI_Command_Handler")

class AICommandHandler:
    """
    Unified handler for AI command detection and execution.
    Handles DOM monitoring and command execution via WebSocket.
    """
    
    # Command prefixes that are recognized
    COMMAND_PREFIXES = ("CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:")
    
    def __init__(self, chrome_path, chrome_driver_path, ws_port=8765):
        self.chrome_path = chrome_path
        self.chrome_driver_path = chrome_driver_path
        self.ws_port = ws_port
        self.ws_uri = f"ws://127.0.0.1:{ws_port}/ws"
        self.log_file = "command_log.txt"
        self.conversation_log = "conversation_log.txt"  # Új beszélgetés log fájl
        
        # Command tracking variables
        self.last_command = ""
        self.last_timestamp = 0
        self.command_cooldown = 3  # seconds
        self.recent_commands = set()  # Store recent commands
        self.max_recent_commands = 5  # Keep track of last 5 commands
        
        # New: Failed commands tracking
        self.failed_commands = {}  # Dict to track failed command attempts
        self.max_retries = 3  # Maximum number of retries per command
        
        # Command history for REPLAY functionality
        self.command_history = []
        self.max_history_size = 10
        
        # Initialize ReplayManager
        self.replay_manager = ReplayManager()
        
        # Add OpenAI client initialization
        self.openai_client = None
        self._initialize_openai()
        
        # Initialize browser connection
        self._initialize_browser()
        
        # Initialize cache
        self.cache_file = "ai_command_cache.pkl"
        self.cache = self._load_cache()
        
        # System command registry - parancsok helyben futtatásához
        self.system_commands = {
            "echo": self._cmd_echo,
            "time": self._cmd_time,
            "date": self._cmd_date,
            "whoami": self._cmd_whoami,
            "hostname": self._cmd_hostname,
            "dir": self._cmd_dir,
            "ls": self._cmd_dir,  # alias for dir
            "help": self._cmd_help,
            "info": self._cmd_info,
            "stats": self._cmd_stats,
            "history": self._cmd_history,
            "cat": self._cmd_cat,
            "type": self._cmd_cat,  # alias for cat
        }
        
        # Performance optimizer
        self.last_dom_scan = 0
        self.dom_scan_interval = 0.3  # seconds
        self.command_stats = {
            "total_commands": 0,
            "system_commands": 0,
            "api_calls": 0,
            "cached_responses": 0,
            "errors": 0
        }

    def _is_system_command(self, cmd: str) -> bool:
        """Eldönti, hogy a parancs egy ismert rendszerparancs-e."""
        if not cmd:
            return False
            
        cmd_parts = cmd.strip().lower().split(None, 1)
        if not cmd_parts:
            return False
            
        base_cmd = cmd_parts[0]
        return base_cmd in self.system_commands

    def _is_json(self, text: str) -> bool:
        """Ellenőrzi, hogy egy szöveg érvényes JSON-e."""
        if not text:
            return False
            
        text = text.strip()
        if not (text.startswith('{') and text.endswith('}')) and not (text.startswith('[') and text.endswith(']')):
            return False
            
        try:
            json.loads(text)
            return True
        except Exception:
            return False
            
    def _calculate_cache_key(self, input_text):
        """Kiszámítja az intelligens cache kulcsot egy bemenethez."""
        # Először normalizáljuk a bemenetet
        normalized = re.sub(r'\s+', ' ', input_text.strip().lower())
        # Hash kiszámítása
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
            
    def _load_cache(self):
        """Betölti a cache-t a cache fájlból."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    cache = pickle.load(f)
                logger.info(f"Loaded {len(cache)} entries from cache")
                return cache
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            
        return {}  # Üres cache új indításkor vagy hiba esetén
        
    def _save_cache(self):
        """Elmenti a cache-t a cache fájlba."""
        try:
            # Limit cache size to 1000 entries
            if len(self.cache) > 1000:
                # Remove oldest entries
                keys_to_remove = sorted(self.cache.keys(), 
                                      key=lambda k: self.cache[k].get('timestamp', 0))[:len(self.cache) - 1000]
                for key in keys_to_remove:
                    del self.cache[key]
                    
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
            logger.debug(f"Saved {len(self.cache)} entries to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            
    def _add_to_cache(self, input_text, response):
        """Hozzáad egy választ a cache-hez."""
        try:
            cache_key = self._calculate_cache_key(input_text)
            self.cache[cache_key] = {
                'response': response,
                'timestamp': time.time(),
                'input': input_text
            }
            
            # Save cache periodically - every 10 cache updates
            if len(self.cache) % 10 == 0:
                self._save_cache()
                
            self.command_stats["cached_responses"] += 1
        except Exception as e:
            logger.error(f"Failed to add to cache: {e}")
            
    def _get_from_cache(self, input_text):
        """Megpróbál választ találni a cache-ben."""
        try:
            cache_key = self._calculate_cache_key(input_text)
            if cache_key in self.cache:
                # Only return cache if not too old (7 days)
                entry = self.cache[cache_key]
                if time.time() - entry.get('timestamp', 0) < 7 * 24 * 3600:
                    logger.info(f"Cache hit for: {input_text[:30]}...")
                    return entry.get('response')
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            
        return None

    # System command implementations
    def _cmd_echo(self, args):
        """Visszaadja a kapott szöveget (echo parancs)."""
        return args if args else ""
        
    def _cmd_time(self, args):
        """Visszaadja a pontos időt."""
        return datetime.now().strftime("%H:%M:%S")
        
    def _cmd_date(self, args):
        """Visszaadja a mai dátumot."""
        return datetime.now().strftime("%Y-%m-%d")
        
    def _cmd_whoami(self, args):
        """Visszaadja a felhasználó nevét."""
        try:
            import getpass
            return getpass.getuser()
        except:
            return os.environ.get('USERNAME', 'unknown')
            
    def _cmd_hostname(self, args):
        """Visszaadja a számítógép nevét."""
        try:
            return socket.gethostname()
        except:
            return "unknown"
            
    def _cmd_dir(self, args):
        """Listázza a megadott könyvtár tartalmát vagy az aktuális könyvtárat."""
        path = args.strip() if args else "."
        try:
            items = os.listdir(path)
            result = []
            for item in items:
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    item += "/"
                result.append(item)
            return "\n".join(sorted(result))
        except Exception as e:
            return f"Hiba: {str(e)}"
            
    def _cmd_help(self, args):
        """Megjeleníti a parancsok listáját súgóval."""
        commands = {
            "echo": "Visszaadja a megadott szöveget (például: echo szöveg)",
            "time": "Kiírja az aktuális időt",
            "date": "Kiírja a mai dátumot",
            "whoami": "Megmutatja a felhasználó nevét",
            "hostname": "Megmutatja a számítógép nevét",
            "dir/ls": "Listázza a könyvtár tartalmát (dir [útvonal])",
            "help": "Megjeleníti ezt a súgót",
            "info": "Információt ad a rendszerről",
            "stats": "Parancsvégrehajtási statisztikák",
            "history": "Előző parancsok listázása",
            "cat/type": "Fájl tartalmának megjelenítése (cat [fájlnév])"
        }
        
        result = "Elérhető parancsok:\n\n"
        for cmd, desc in commands.items():
            result += f"{cmd} - {desc}\n"
            
        return result
        
    def _cmd_info(self, args):
        """Rendszerinformáció megjelenítése."""
        import platform
        py_version = platform.python_version()
        os_info = platform.platform()
        
        result = [
            f"AI Command Handler verzió: 1.2.0",
            f"Python verzió: {py_version}",
            f"Operációs rendszer: {os_info}",
            f"Cache mérete: {len(self.cache)} bejegyzés",
            f"Parancs előzmények: {len(self.command_history)} bejegyzés",
            f"Könyvtár: {os.getcwd()}"
        ]
        
        return "\n".join(result)
        
    def _cmd_stats(self, args):
        """Parancs statisztikák megjelenítése."""
        result = [
            f"Összes parancs: {self.command_stats['total_commands']}",
            f"Rendszerparancsok: {self.command_stats['system_commands']}",
            f"API hívások: {self.command_stats['api_calls']}",
            f"Cache találatok: {self.command_stats['cached_responses']}",
            f"Hibák: {self.command_stats['errors']}"
        ]
        
        return "\n".join(result)
        
    def _cmd_history(self, args):
        """Parancs előzmények megjelenítése."""
        if not self.command_history:
            return "Nincs parancselőzmény."
            
        result = []
        for i, cmd in enumerate(self.command_history):
            # Rövidítsük le a parancsokat ha túl hosszúak
            truncated = cmd[:50] + "..." if len(cmd) > 50 else cmd
            result.append(f"{i+1}. {truncated}")
            
        return "\n".join(result)
        
    def _cmd_cat(self, args):
        """Fájl tartalmának megjelenítése."""
        if not args:
            return "Használat: cat [fájlnév]"
            
        filepath = args.strip()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ha túl hosszú a fájl, csak az elejét jelenítsük meg
            if len(content) > 1000:
                content = content[:1000] + "...\n[A fájl további része levágva]"
                
            return content
        except Exception as e:
            return f"Hiba a fájl olvasásakor: {str(e)}"
            
    def _run_system_command(self, cmd: str) -> str:
        """Rendszerparancs futtatása subprocess-szel vagy a belső parancskezelővel."""
        print(f"DEBUG - Rendszerparancs végrehajtása: {cmd}")
        
        self.command_stats["total_commands"] += 1
        self.command_stats["system_commands"] += 1
        
        # Speciális "diagnose network" parancs kezelése
        if cmd.strip().lower() == "diagnose network":
            try:
                print("DEBUG - Hálózati diagnosztika indítása")
                logger.info("Hálózati diagnosztika indítása a network_diagnostics modul segítségével")
                
                # Importáljuk és futtassuk a network_diagnostics modult
                try:
                    from core.network_diagnostics import main
                    result = main()
                    return result or "Hálózati diagnosztika sikeresen végrehajtva"
                except ImportError:
                    return "Hiba: A network_diagnostics modul nem található. Kérjük, ellenőrizze, hogy létezik-e a core/network_diagnostics.py fájl."
                except Exception as e:
                    return f"Hiba a hálózati diagnosztika futtatásakor: {str(e)}"
            except Exception as e:
                self.command_stats["errors"] += 1
                return f"Hálózati diagnosztika hiba: {str(e)}"
        
        # Ellenőrizzük, hogy a parancs egy JSON formátumú objektum-e
        if self._is_json(cmd):
            try:
                cmd_obj = json.loads(cmd)
                # Ha a parancs érték egy string, és szerepel a COMMAND_LIBRARY-ben
                if isinstance(cmd_obj, dict) and "parancs" in cmd_obj:
                    cmd_name = cmd_obj["parancs"]
                    # Ellenőrizzük, hogy a parancs neve szerepel-e a COMMAND_LIBRARY-ben
                    if cmd_name in COMMAND_LIBRARY:
                        # Helyettesítsük be a konkrét parancs szövegével és végrehajtsuk
                        logger.info(f"Parancskönyvtár használata: {cmd_name}")
                        # Ha van paramétere a parancsnak
                        params = cmd_obj.get("paraméterek", "")
                        # A COMMAND_LIBRARY-ban tárolt függvény meghívása
                        return COMMAND_LIBRARY[cmd_name](params)
            except Exception as e:
                logger.error(f"Hiba a JSON parancs feldolgozásakor: {str(e)}")
                self.command_stats["errors"] += 1
                return f"Hiba a parancs feldolgozása során: {str(e)}"
        
        # Először ellenőrizzük, hogy van-e belső parancskezelőnk a parancshoz
        parts = cmd.strip().split(None, 1)
        base_cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        
        # Belső parancskezelők használata, ha létezik
        if base_cmd and base_cmd in self.system_commands:
            try:
                return self.system_commands[base_cmd](args)
            except Exception as e:
                return f"Hiba a parancs végrehajtása közben: {str(e)}"
        
        # Ellenőrizzük, hogy a parancs szerepel-e a COMMAND_LIBRARY-ben
        if base_cmd in COMMAND_LIBRARY:
            try:
                return COMMAND_LIBRARY[base_cmd](args)
            except Exception as e:
                self.command_stats["errors"] += 1
                return f"Hiba a parancs végrehajtása közben: {str(e)}"
        
        # Ha nincs belső kezelő, külső parancsként futtatjuk
        try:
            # Security precaution: Avoid running extremely long commands
            if len(cmd) > 200:
                return "Hiba: Túl hosszú rendszerparancs."
            
            # Basic check for potentially harmful commands
            harmful_patterns = ["rm ", "del ", ":(){:|:&};:", "format ", "shutdown"]
            if any(pattern in cmd.lower() for pattern in harmful_patterns):
                 return "Hiba: Potenciálisan veszélyes parancs blokkolva."

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15, encoding='utf-8', errors='ignore')
            output = result.stdout.strip() or result.stderr.strip()
            
            # Limit output length
            max_output_len = 1000
            if len(output) > max_output_len:
                output = output[:max_output_len] + "... [kimenet levágva]"
            
            return output if output else "(Nincs kimenet)"
        except subprocess.TimeoutExpired:
            return "Hiba: Rendszerparancs időtúllépés."
        except Exception as e:
            self.command_stats["errors"] += 1
            return f"Rendszerparancs hiba: {str(e)}"

    async def _send_openai_request(self, command):
        """OpenAI API-n keresztül küld egy kérést, cache-eléssel."""
        # Try to get from cache first
        cached_response = self._get_from_cache(command)
        if cached_response is not None:
            logger.info("Using cached response")
            return cached_response
        
        # If not in cache, call OpenAI API
        try:
            if not self.openai_client:
                return "OpenAI API nem elérhető - API kulcs nincs beállítva"
                
            self.command_stats["api_calls"] += 1
            
            # Format the command for a chat completion
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",  # Használjunk egy gyorsabb és olcsóbb modellt alapból
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Respond concisely."},
                    {"role": "user", "content": command}
                ],
                temperature=0.7,
                max_tokens=500  # Limit token size for faster responses
            )
            
            result = response.choices[0].message.content.strip()
            
            # Add to cache for future use
            self._add_to_cache(command, result)
            
            return result
        except Exception as e:
            logger.error(f"OpenAI API Error: {str(e)}")
            self.command_stats["errors"] += 1
            return f"Hiba az OpenAI API hívás során: {str(e)}"

    async def apply_code_edit(self, file_path: str, instruction: str) -> bool:
        """
        Apply code edits to a Python file using GPT-4.
        Uses caching for similar instructions to avoid unnecessary API calls.
        
        Args:
            file_path: Path to the Python file to edit
            instruction: Natural language instruction for the edit
            
        Returns:
            bool: True if successful, False otherwise
        """
        cache_key = f"code_edit:{file_path}:{instruction}"
        cached_result = self._get_from_cache(cache_key)
        
        if cached_result:
            logger.info(f"Using cached code edit for {file_path}")
            # Apply the cached edit
            try:
                path = pathlib.Path(file_path)
                output_path = path.parent / f"{path.stem}_ai{path.suffix}"
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(cached_result)
                    
                logger.info(f"Applied cached code edit to {output_path}")
                return True
            except Exception as e:
                logger.error(f"Error applying cached edit: {e}")
                return False

        if not self.openai_client:
            logger.error("OpenAI client not initialized - check API key configuration")
            return False

        try:
            # Read the source file
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Create prompt for GPT-4
            prompt = f"""Please modify the following Python code according to this instruction:
            {instruction}
            
            Here is the code:
            ```python
            {source_code}
            ```
            
            Please provide ONLY the modified code without any explanations."""

            self.command_stats["api_calls"] += 1

            # Get GPT-4 response
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a Python code editing assistant. Provide only the modified code without explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            # Extract the modified code
            modified_code = response.choices[0].message.content.strip()
            if modified_code.startswith("```python"):
                modified_code = modified_code[10:-3].strip()
            elif modified_code.startswith("```"):
                modified_code = modified_code[3:-3].strip()

            # Generate output filename
            path = pathlib.Path(file_path)
            output_path = path.parent / f"{path.stem}_ai{path.suffix}"

            # Save modified code
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(modified_code)

            # Store in cache
            self._add_to_cache(cache_key, modified_code)

            # Log the change
            with open('openai_agent.log', 'a', encoding='utf-8') as f:
                log_entry = f"[{datetime.now().isoformat()}] Modified {file_path} -> {output_path}\n"
                f.write(log_entry)

            # Add journal entry
            journal_entry = f"""
## Code Edit {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Source: `{file_path}`
- Output: `{output_path}`
- Instruction: {instruction}
"""
            with open('copilot_journal.md', 'a', encoding='utf-8') as f:
                f.write(journal_entry)

            logger.info(f"Successfully applied code edit: {file_path} -> {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error applying code edit: {e}")
            self.command_stats["errors"] += 1
            return False

    def _initialize_browser(self):
        """Initialize connection to an existing Chrome instance"""
        try:
            logger.info("Initializing browser connection...")
            
            # Try to connect to running browser with debugger port
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            
            service = Service(executable_path=self.chrome_driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            logger.info(f"Successfully connected to browser: {self.driver.title}")
        except Exception as e:
            # If connection fails, launch a new browser instance
            logger.warning(f"Could not connect to existing browser: {e}")
            self._launch_new_browser()
    
    def _launch_new_browser(self):
        """Launch a new Chrome instance with remote debugging enabled"""
        try:
            logger.info("Launching new browser instance...")
            url = "https://chat.openai.com"
            port = 9222
            
            def open_chrome():
                subprocess.Popen([
                    self.chrome_path,
                    f'--remote-debugging-port={port}',
                    '--user-data-dir=remote-profile',
                    url
                ])
            
            threading.Thread(target=open_chrome).start()
            time.sleep(3)  # Wait for browser to start
            
            # Connect to the newly launched browser
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            
            service = Service(executable_path=self.chrome_driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            logger.info("Browser launched. Waiting for user to log in...")
            input("Press Enter once you've logged in to ChatGPT...")
            
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise
    
    def _initialize_openai(self):
        """Initialize OpenAI client if API key is configured"""
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if (api_key):
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
            else:
                logger.warning("OPENAI_API_KEY environment variable not set")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")

    async def apply_code_edit(self, file_path: str, instruction: str) -> bool:
        """
        Apply code edits to a Python file using GPT-4.
        
        Args:
            file_path: Path to the Python file to edit
            instruction: Natural language instruction for the edit
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.openai_client:
            logger.error("OpenAI client not initialized - check API key configuration")
            return False

        try:
            # Read the source file
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Create prompt for GPT-4
            prompt = f"""Please modify the following Python code according to this instruction:
            {instruction}
            
            Here is the code:
            ```python
            {source_code}
            ```
            
            Please provide ONLY the modified code without any explanations."""

            # Get GPT-4 response
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a Python code editing assistant. Provide only the modified code without explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            # Extract the modified code
            modified_code = response.choices[0].message.content.strip()
            if modified_code.startswith("```python"):
                modified_code = modified_code[10:-3].strip()
            elif modified_code.startswith("```"):
                modified_code = modified_code[3:-3].strip()

            # Generate output filename
            path = pathlib.Path(file_path)
            output_path = path.parent / f"{path.stem}_ai{path.suffix}"

            # Save modified code
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(modified_code)

            # Log the change
            with open('openai_agent.log', 'a', encoding='utf-8') as f:
                log_entry = f"[{datetime.now().isoformat()}] Modified {file_path} -> {output_path}\n"
                f.write(log_entry)

            # Add journal entry
            journal_entry = f"""
## Code Edit {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Source: `{file_path}`
- Output: `{output_path}`
- Instruction: {instruction}
"""
            with open('copilot_journal.md', 'a', encoding='utf-8') as f:
                f.write(journal_entry)

            logger.info(f"Successfully applied code edit: {file_path} -> {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error applying code edit: {e}")
            return False

    def detect_commands(self):
        """
        Scan the DOM for AI commands using multiple detection strategies.
        Returns the most recent valid command or empty string if none found.
        """
        command = ""
        now = time.time()
        
        try:
            # Keressük a felhasználói és asszisztens üzeneteket
            try:
                user_messages = self.driver.find_elements(By.CSS_SELECTOR, "div[data-message-author-role='user']")
                assistant_messages = self.driver.find_elements(By.CSS_SELECTOR, "div[data-message-author-role='assistant']")
                
                # Mentsük el az új üzeneteket
                for msg in user_messages:
                    text = msg.text.strip()
                    if text and not self._is_message_logged(text):
                        self.log_conversation("USER", text)
                        
                for msg in assistant_messages:
                    text = msg.text.strip()
                    if text and not self._is_message_logged(text):
                        self.log_conversation("ASSISTANT", text)
            except Exception as e:
                if "Invalid session id" in str(e):
                    logger.warning("Browser session invalid, attempting to reconnect...")
                    self._reconnect_browser()
                    return ""
                # Other errors we will just log but continue with command detection strategies
                logger.debug(f"Error scanning messages: {e}")
            
            last_detected_command = None
            
            # Strategy 1: Look for assistant role messages in ChatGPT
            command = self._detect_from_assistant_role()
            if command:
                last_detected_command = command
                
            # Strategy 2: Look for text-base class (works in Copilot)
            command = self._detect_from_text_base()
            if command:
                # If we found a different command, it might be newer
                if command != last_detected_command:
                    last_detected_command = command
                
            # Strategy 3: Try generic markdown content
            command = self._detect_from_markdown()
            if command:
                if command != last_detected_command:
                    last_detected_command = command
                
            # Strategy 4: Direct JavaScript execution to scan all content
            command = self._detect_via_javascript()
            if command:
                if command != last_detected_command:
                    last_detected_command = command
            
            # Only process command if it passes validation
            if last_detected_command and self._is_new_command(last_detected_command, now):
                return last_detected_command
            
        except Exception as e:
            if "Invalid session id" in str(e):
                logger.warning("Browser session invalid, attempting to reconnect...")
                self._reconnect_browser()
            else:
                logger.error(f"Error detecting commands: {e}")
        
        return ""
    
    def _detect_from_assistant_role(self):
        """Detect commands from assistant role elements (ChatGPT)"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "div[data-message-author-role='assistant'] div.markdown")
            for el in reversed(elements):
                text = el.text.strip()
                if text.startswith(self.COMMAND_PREFIXES):
                    return text
        except Exception as e:
            logger.debug(f"Error in assistant role detection: {e}")
        return ""
    
    def _detect_from_text_base(self):
        """Detect commands from text-base class elements (Copilot)"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "div.text-base")
            for el in reversed(elements):
                text = el.text.strip()
                if text.startswith(self.COMMAND_PREFIXES):
                    return text
        except Exception as e:
            logger.debug(f"Error in text-base detection: {e}")
        return ""
    
    def _detect_from_markdown(self):
        """Detect commands from markdown elements (general)"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, ".markdown, .prose")
            for el in reversed(elements):
                text = el.text.strip()
                if text.startswith(self.COMMAND_PREFIXES):
                    return text
        except Exception as e:
            logger.debug(f"Error in markdown detection: {e}")
        return ""
    
    def _detect_via_javascript(self):
        """Use JavaScript to scan for commands in the DOM"""
        try:
            script = """
            const prefixes = ["CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:"];
            let allTextElements = document.querySelectorAll('div, p, span, pre');
            
            for (let i = allTextElements.length - 1; i >= 0; i--) {
                const text = allTextElements[i].textContent.trim();
                for (const prefix of prefixes) {
                    if (text.startsWith(prefix)) {
                        return text;
                    }
                }
            }
            return "";
            """
            
            return self.driver.execute_script(script)
        except Exception as e:
            logger.debug(f"Error in JavaScript detection: {e}")
        return ""
    
    def _is_new_command(self, command, now):
        """Check if a command is new and should be processed"""
        if not command:
            return False
            
        # Check if command starts with valid prefix
        if not command.startswith(self.COMMAND_PREFIXES):
            return False
            
        # Get the prefix that matched
        prefix = next((p for p in self.COMMAND_PREFIXES if command.startswith(p)), "")
        
        # Ignore commands that are too short (just the prefix)
        if len(command.strip()) <= len(prefix):
            return False
            
        # Speciális "FORCE" parancsok mindig lefutnak, még ismétlés esetén is
        # Formátum: CMD: FORCE:parancs - ez felülírja a duplikáció ellenőrzést
        if command.startswith("CMD:") and "FORCE:" in command[:15]:
            # Kivesszük a "FORCE:" részt a parancsból a további feldolgozáshoz
            command_content = command.replace("FORCE:", "", 1)
            # Update timestamp still
            self.last_timestamp = now
            return True
            
        # Special handling for CODE: commands
        if command.startswith("CODE:"):
            # Must contain actual code content
            code_content = command.split("CODE:", 1)[1].strip()
            if len(code_content) < 10:  # Minimum meaningful code length
                return False
                
            # If multiline, must have proper ending
            if "\n" in code_content:
                code_lines = code_content.strip().split("\n")
                if len(code_lines) < 2:  # Need at least 2 lines for multiline code
                    return False
                    
                # Look for code block markers
                markers = ["```", "```python", "```py"]
                has_markers = any(code_content.strip().endswith(m) for m in markers)
                if not has_markers and not code_content.strip().endswith((";", "}", ")", "]")):
                    return False
                    
            # Longer cooldown for CODE: commands
            if (now - self.last_timestamp) <= self.command_cooldown * 3:
                return False
                
        # Special handling for CMD: commands
        elif command.startswith("CMD:"):
            # Must contain meaningful command content (at least 5 characters after prefix)
            cmd_content = command.split("CMD:", 1)[1].strip()
            if len(cmd_content) < 3:  # Require at least 3 characters for a meaningful command
                return False
                
        # Special handling for FILE: commands
        elif command.startswith("FILE:"):
            # Must contain meaningful file operation
            file_content = command.split("FILE:", 1)[1].strip()
            if len(file_content) < 4:  # Minimum length for a valid file operation like "read x"
                return False
                
        # Special handling for INFO: commands
        elif command.startswith("INFO:"):
            # INFO commands can be shorter, but still need some content
            info_content = command.split("INFO:", 1)[1].strip()
            if not info_content:  # At least some content is required
                return False
            
        # For all commands, enforce cooldown
        if (now - self.last_timestamp) <= self.command_cooldown:
            return False
        
        # Check if command was recently processed
        if command in self.recent_commands:
            return False
        
        # Add to recent commands and update timestamp
        self.recent_commands.add(command)
        if len(self.recent_commands) > self.max_recent_commands:
            self.recent_commands.pop()
            
        # Update timestamp only if we're actually going to process this command
        self.last_timestamp = now
        
        return True

    def _is_error_response(self, response: str) -> bool:
        """
        Ellenőrzi, hogy a válasz hibaüzenet-e.
        
        Args:
            response (str): A parancs végrehajtásának válasza
            
        Returns:
            bool: True ha hibaüzenet, False ha nem
        """
        error_indicators = [
            "Error",
            "not recognized",
            "failed",
            "Permission denied",
            "Cannot find",
            "Invalid",
            "WebSocket error"
        ]
        return any(indicator.lower() in response.lower() for indicator in error_indicators)

    def _get_command_index(self, command: str) -> int:
        """
        Megkeresi egy parancs indexét a command_history listában.
        
        Args:
            command (str): A keresett parancs
            
        Returns:
            int: A parancs 1-alapú indexe a history-ban, vagy -1 ha nincs találat
        """
        try:
            # Keresés a history-ban
            if command in self.command_history:
                # 1-alapú index visszaadása (REPLAY:1 az első parancsra)
                return self.command_history.index(command) + 1
            return -1
        except Exception as e:
            logger.error(f"Hiba a parancs index keresésekor: {str(e)}")
            return -1

    async def handle_replay(self, index):
        """
        REPLAY parancs kezelése.
        
        Args:
            index (int): A végrehajtandó parancs indexe a history-ban (1-alapú)
            
        Returns:
            str: A parancs végrehajtásának eredménye
        """
        command_entry = self.replay_manager.get_command(index)
        if command_entry:
            original_command = command_entry["command"]
            logger.info(f"Replaying command {index}: {original_command}")
            return await self.send_command_to_websocket(original_command)
        else:
            error_msg = f"REPLAY sikertelen - érvénytelen index: {index}"
            logger.error(error_msg)
            return error_msg

    def _add_to_history(self, command):
        """Add a command to history, maintaining max size"""
        if command and not command.startswith("REPLAY:"):
            # Csak akkor adjuk hozzá, ha még nincs benne
            if command not in self.command_history:
                self.command_history.insert(0, command)  # Add to front
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()  # Remove oldest
                logger.info(f"Command added to history: {command[:50]}...")

    async def send_command_to_websocket(self, command):
        """Send a command to the WebSocket server"""
        max_retries = 5
        retry_delay = 1
        
        # Ne számoljuk a REPLAY parancsokat a hibák közé
        is_replay = command.startswith("REPLAY:")
        original_command = command
        
        # Ha nem REPLAY parancs, adjuk hozzá a history-hoz
        if not is_replay:
            self.replay_manager.add_command(command, "", True)  # Initially mark as successful
        
        # WebSocket kapcsolat és parancs küldése
        for attempt in range(max_retries):
            try:
                async with websockets.connect(
                    self.ws_uri,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                    max_size=10485760  # 10MB max message size
                ) as websocket:
                    
                    logger.info(f"WebSocket connected on attempt {attempt + 1}, sending command: {command[:50]}...")
                    
                    # Send ping to verify connection
                    pong_waiter = await websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)
                    logger.info("WebSocket connection verified with ping")
                    
                    # Send command with timeout
                    await asyncio.wait_for(websocket.send(command), timeout=10)
                    logger.info("Command sent, waiting for response...")
                    
                    # Wait for response
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    
                    # Update command status in replay manager
                    if not is_replay:
                        success = not self._is_error_response(response)
                        self.replay_manager.add_command(command, response, success)
                        
                        if not success and self.replay_manager.should_retry(command):
                            logger.info(f"Command failed, triggering automatic retry...")
                            # Get command entry to retry
                            command_entry = self.replay_manager.get_command_by_content(command)
                            if command_entry:
                                return await self.handle_replay(command_entry["index"])
                    
                    return response
                    
            except Exception as e:
                logger.error(f"WebSocket attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"WebSocket connection failed after {max_retries} attempts. Last error: {e}"
                    logger.error(error_msg)
                    if not is_replay:
                        self.replay_manager.add_command(command, error_msg, False)
                    return error_msg

    def send_response_via_selenium(self, message):
        """
        Send response back to ChatGPT using Selenium JavaScript injection.
        Uses multiple fallback strategies to ensure reliable response submission.
        """
        try:
            logger.info("Sending response via Selenium...")
            
            # Sanitize response to handle emojis and special characters
            message = self._sanitize_text(message)
            
            # Add system identifier prefix to the message
            message = "[SYSID:AI123] " + message
            
            # Find textarea using the most specific selectors first
            textarea_selectors = [
                "#prompt-textarea",  # New ChatGPT primary selector
                "textarea[data-id='prompt-textarea']",
                "textarea.m-0",  # New ChatGPT specific class
                "textarea[placeholder*='Send a message']",  # Placeholder text
                "textarea[tabindex='0']",  # Accessibility attribute
                "textarea"  # Generic fallback
            ]
            
            textarea = None
            for selector in textarea_selectors:
                try:
                    textarea = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if textarea:
                        logger.info(f"Found textarea with selector: {selector}")
                        break
                except:
                    continue
            
            if not textarea:
                logger.error("Could not find textarea element")
                return False

            # First make sure the textarea is in view and interactable
            self.driver.execute_script("""
                arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            """, textarea)
            time.sleep(1)  # Wait for scroll and any animations
            
            # Clear the textarea first
            try:
                textarea.clear()
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not clear textarea normally: {e}")
                # Try with JavaScript
                try:
                    self.driver.execute_script("arguments[0].value = '';", textarea)
                except Exception as e:
                    logger.error(f"Failed to clear textarea: {e}")
            
            # Try three approaches to input text, in order of preference:
            
            # 1. First try direct send_keys method (most reliable)
            try:
                # Send entire message at once
                textarea.send_keys(message)
                logger.info("Entered text using send_keys method")
                success = True
            except Exception as e:
                logger.warning(f"Could not use send_keys to input text: {e}")
                success = False
            
            # 2. If send_keys failed, try JavaScript approach
            if not success:
                try:
                    self.driver.execute_script("""
                        const textarea = arguments[0];
                        const response = arguments[1];
                        
                        // Force clear and set value
                        textarea.value = '';
                        textarea.value = response;
                        
                        // Trigger all relevant events
                        const events = ['input', 'change', 'keyup', 'keydown', 'keypress'];
                        events.forEach(eventType => {
                            textarea.dispatchEvent(new Event(eventType, { bubbles: true }));
                        });
                        
                        // Force enable any submit buttons
                        document.querySelectorAll('button[type="submit"], button[data-testid="send-button"]')
                            .forEach(btn => btn.disabled = false);
                    """, textarea, message)
                    logger.info("Entered text using JavaScript method")
                    success = True
                except Exception as e:
                    logger.error(f"Error setting textarea value with JavaScript: {e}")
                    success = False
            
            # 3. Last resort - try to paste text from clipboard
            if not success:
                try:
                    import pyperclip
                    pyperclip.copy(message)
                    
                    # Use keyboard shortcut to paste
                    textarea.send_keys(Keys.CONTROL, 'v')
                    time.sleep(0.5)
                    logger.info("Entered text using clipboard paste method")
                    success = True
                except Exception as e:
                    logger.error(f"Failed to paste text from clipboard: {e}")
                    success = False
            
            if not success:
                logger.error("All text input methods failed")
                return False
            
            # Give the UI a moment to update
            time.sleep(1)

            # Find and click submit button - VÁLTOZÁS 1: WebDriverWait a DOM frissülés kezelésére
            send_button = None
            button_selectors = [
                "button[data-testid='send-button']",
                "button.absolute.p-1",  # New ChatGPT send button class
                "button[class*='bottom-right']",
                "button[type='submit']"
            ]
            
            for selector in button_selectors:
                try:
                    send_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if send_button:
                        logger.info(f"Found submit button with selector: {selector}")
                        break
                except:
                    continue
            
            if send_button:
                try:
                    # Try clicking with JavaScript
                    self.driver.execute_script("arguments[0].click();", send_button)
                    logger.info("Successfully clicked send button")
                    time.sleep(1)
                    return True  # VÁLTOZÁS 2: return True hozzáadva, hogy ne próbálkozzon másik módszerrel
                except Exception as e:
                    logger.error(f"Failed to click send button: {e}")
            
            # If button click failed, try Enter key as last resort
            try:
                textarea.send_keys(Keys.RETURN)
                logger.info("Sent response using Enter key")
                time.sleep(1)
                return True
            except Exception as e:
                logger.error(f"Failed to send with Enter key: {e}")
                
                # One last attempt - try clicking the button with action chains
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(send_button).click().perform()
                    logger.info("Clicked send button using ActionChains")
                    time.sleep(1)
                    return True
                except Exception as e2:
                    logger.error(f"Failed to click with ActionChains: {e2}")
                    return False
                
        except Exception as e:
            logger.error(f"Error sending response via Selenium: {e}")
            return False
            
    def _sanitize_text(self, text):
        """Sanitize text to handle emojis and special characters"""
        try:
            # Replace problematic emojis with their text equivalents
            emoji_map = {
                '✔️': '[OK]',
                '🔍': '[SEARCH]',
                '⭐': '[STAR]',
                '🚀': '[ROCKET]',
                '📝': '[WRITE]',
                '⏳': '[TIMER]',
                '✅': '[CHECK]',
                '❌': '[X]',
                '⚠️': '[WARNING]',
                '💫': '[SPARKLE]',
                '🔥': '[FIRE]',
                '🌟': '[GLOW]',
                '🌍': '[EARTH]'
            }
            
            for emoji, replacement in emoji_map.items():
                text = text.replace(emoji, replacement)
            
            # Remove any remaining non-BMP characters
            return ''.join(c for c in text if ord(c) < 0x10000)
        except:
            return text
    
    def log_command(self, command, response):
        """Log command and response to file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] COMMAND: {command}\n")
                f.write(f"[{timestamp}] RESPONSE: {response[:300]}\n\n")
        except Exception as e:
            logger.error(f"Error logging command: {e}")
    
    def log_conversation(self, role, message):
        """Log teljes beszélgetés mentése"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.conversation_log, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {role}: {message}\n")
        except Exception as e:
            logger.error(f"Hiba a beszélgetés mentésekor: {e}")

    def _is_message_logged(self, message):
        """Ellenőrzi, hogy az üzenet már mentve van-e"""
        try:
            if not os.path.exists(self.conversation_log):
                return False
                
            with open(self.conversation_log, "r", encoding="utf-8") as f:
                content = f.read()
                # Csak az üzenet tartalmat keressük, timestamp nélkül
                return message in content
        except Exception:
            return False

    def handle_replay_command(self, command):
        """Handle replay commands to replay previous responses"""
        try:
            # Extract index from REPLAY:X format
            index = int(command.split(":")[1].strip())
            
            # Read log file and find the Xth command
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            count = 0
            for i in range(len(lines)):
                if "COMMAND:" in lines[i]:
                    count += 1
                    if count == index:
                        # Found the command, next line should be the response
                        if i + 1 < len(lines) and "RESPONSE:" in lines[i + 1]:
                            response = lines[i + 1].split("RESPONSE:")[1].strip()
                            logger.info(f"Replaying response #{index}: {response[:50]}...")
                            return response
            
            return f"Could not find replay #{index} in logs"
        except Exception as e:
            logger.error(f"Error handling replay: {e}")
            return f"Error processing replay: {e}"
    
    def _is_code_edit_command(self, command: str) -> bool:
        """Check if command is a natural language code edit request"""
        if not command.upper().startswith("CMD:"):
            return False
            
        # Hungarian edit keywords (case insensitive)
        edit_keywords = [
            "módosítsd", "javítsd", "írd át",
            "modositsd", "javitsd", "ird at",
            "változtasd", "valtoztasd"
        ]
        
        cmd_text = command[4:].lower().strip()
        return any(keyword in cmd_text.lower() for keyword in edit_keywords)

    def _extract_file_and_instruction(self, command: str) -> tuple[str, str]:
        """Extract file path and instruction from code edit command"""
        # Remove CMD: prefix
        content = command[4:].strip()
        
        # Look for file path patterns
        import re
        file_patterns = [
            r'"([^"]+\.py)"',  # Quoted path
            r'\'([^\']+\.py)\'',  # Single quoted path
            r'([^\s]+\.py)',  # Unquoted .py file
        ]
        
        file_path = None
        for pattern in file_patterns:
            match = re.search(pattern, content)
            if match:
                file_path = match.group(1)
                # Remove the file path from content to get instruction
                content = re.sub(pattern, '', content, 1).strip()
                break
                
        if not file_path:
            logger.error("No Python file path found in command")
            return None, None
            
        # Clean up the instruction
        instruction = content.strip()
        
        return file_path, instruction

    def is_scheduled_command(self, message: str) -> bool:
        """Detect if the message contains natural language time expressions."""
        time_keywords = ["óra", "perc", "másodperc"]
        return any(keyword in message for keyword in time_keywords)

    def extract_schedule_delay(self, message: str) -> int:
        """Parse Hungarian time expressions and return delay in seconds."""
        time_patterns = {
            r"(\d+)\s*óra": 3600,  # Hours to seconds
            r"(\d+)\s*perc": 60,   # Minutes to seconds
            r"(\d+)\s*másodperc": 1  # Seconds
        }
        total_seconds = 0
        for pattern, multiplier in time_patterns.items():
            match = re.search(pattern, message)
            if match:
                total_seconds += int(match.group(1)) * multiplier
        return total_seconds

    def schedule_delayed_command(self, file_path: str, instruction: str, delay_seconds: int):
        """Wait for the specified delay and then call apply_code_edit."""
        logger.info(f"Scheduled command for {file_path} in {delay_seconds} seconds.")
        time.sleep(delay_seconds)
        asyncio.run(self.apply_code_edit(file_path, instruction))

    def _is_simple_command(self, command: str) -> bool:
        """
        Ellenőrzi, hogy egy parancs egyszerű rendszerparancs-e, amit helyben tudunk kezelni.
        """
        if not command.startswith("CMD:"):
            return False
            
        # Egyszerű parancsok listája
        simple_commands = [
            "echo", "dir", "ls", "cd", "pwd", "clear",
            "time", "date", "whoami", "hostname", "ping",
            "type", "cat"
        ]
        
        cmd_content = command[4:].strip().lower()
        return any(cmd_content.startswith(cmd) for cmd in simple_commands)

    def _handle_simple_command(self, command: str) -> str:
        """
        Egyszerű parancsok végrehajtása helyben, Python kódban.
        """
        cmd_content = command[4:].trip()
        
        # Echo parancs kezelése
        if cmd_content.lower().startswith("echo"):
            return cmd_content[5:].strip()
            
        # További egyszerű parancsok implementálása...
        # TODO: Több parancs hozzáadása szükség szerint
        
        return f"Simple command executed: {cmd_content}"

    def handle_response(self, response: str, original_command: str = None):
        """Handles the response based on its routed type."""
        response_type = route_response(response)
        print(f"DEBUG - Command: {original_command[:50] if original_command else 'None'}, Response: {response[:50]}..., Routed as: {response_type}")
        
        # JSON válaszoknál speciális kezelés, hogy elkerüljük az ismétlést
        if response_type == "JSON" and original_command and "FORCE:echo" in original_command:
            # Csak egyszer küldjük vissza a választ az echo JSON parancsokra
            print("DEBUG - JSON parancsra válasz küldése")
            self.send_response_via_selenium(response)
            return
        
        # Rendszerparancs kimenete mindig kerüljön visszaküldésre, 
        # függetlenül attól, hogyan kategorizálja a route_response
        if original_command and original_command.startswith("CMD:"):
            cmd_content = original_command[4:].strip()
            # FORCE: prefix eltávolítása a vizsgálathoz
            if cmd_content.startswith("FORCE:"):
                cmd_content = cmd_content[6:].strip()
                
            if self._is_system_command(cmd_content) and response != cmd_content:
                print("DEBUG - Rendszerparancs kimenete, visszaküldés")
                self.send_response_via_selenium(response)
                return
        
        # Egyéb válaszok kezelése típus szerint
        if response_type == "ECHO":
            # Csak akkor ne küldjük vissza, ha pontosan megegyezik az eredeti parancs tartalmával
            if original_command:
                # Tisztítsuk meg a parancsot a FORCE: és CMD: prefixektől
                clean_cmd = original_command
                if clean_cmd.startswith("CMD:"):
                    clean_cmd = clean_cmd[4:].strip()
                if clean_cmd.startswith("FORCE:"):
                    clean_cmd = clean_cmd[6:].strip()
                    
                if response.strip() == clean_cmd.strip():
                    print("DEBUG - Pontos egyezés az eredeti paranccsal, nem küldöm vissza")
                    return
                    
            print("DEBUG - ECHO típusú, de nem egyezik az eredetivel, visszaküldés")
            self.send_response_via_selenium(response)
        elif response_type == "ERROR":
            print("DEBUG - HIBA:", response)
            self.send_response_via_selenium(response)  # Hibaüzenetet is küldjük vissza
        elif response_type in ("CODE", "JSON"):
            print("DEBUG - CODE/JSON típusú, visszaküldés")
            self.send_response_via_selenium(response)
        elif response_type == "UNKNOWN":
            print("DEBUG - UNKNOWN típusú, visszaküldés")
            self.send_response_via_selenium(response)

    async def start_monitoring(self):
        """AI parancsfigyelő főciklus, optimalizált, csak kritikus hibakezeléssel."""
        logger.info("Optimalizált parancskezelő indítása...")
        print("AI Command Handler v1.2.0 elindítva - Optimalizált verzió")
        print("Parancsok figyelése megkezdve...")
        
        while True:
            try:
                # Optimalized polling - only scan DOM at intervals
                now = time.time()
                if now - self.last_dom_scan < self.dom_scan_interval:
                    await asyncio.sleep(0.1)  # Short sleep to prevent CPU hogging
                    continue
                
                self.last_dom_scan = now
                
                # Detect any new commands
                command = self.detect_commands()
                if not command:
                    continue  # No command detected

                logger.info(f"Command detected: {command[:60]}...")
                category = route_response(command)
                print(f"DEBUG - Beérkező parancs kategóriája: {category}")
                response = None
                
                self.command_stats["total_commands"] += 1

                try:
                    # Process command based on category
                    if category == "ECHO" and command.startswith("CMD:"):
                        cmd_content = command[command.find(":")+1:].strip()
                        
                        # Handle system commands directly
                        if self._is_system_command(cmd_content):
                            print(f"DEBUG - Rendszerparancs detektálva: {cmd_content}")
                            response = self._run_system_command(cmd_content)
                            self.send_response_via_selenium(response)
                            self._add_to_history(command)
                            self.log_command(command, response)
                            continue
                            
                        # Handle JSON data
                        elif self._is_json(cmd_content):
                            response = await self._process_json_command(cmd_content)
                        
                        # MÓDOSÍTVA: Az összes CMD: parancsot megpróbáljuk futtatni subprocess-szel
                        else:
                            print(f"DEBUG - Nyers rendszerparancs futtatása: {cmd_content}")
                            response = self._run_system_command(cmd_content)
                            # Ha nincs kimenet, akkor adjunk visszajelzést
                            if not response or response == "(Nincs kimenet)":
                                response = "Parancs végrehajtva, de nincs kimenet."
                            
                    elif category == "JSON":
                        response = await self._process_json_command(command)
                        
                    elif category == "CODE":
                        if self._is_code_edit_command(command):
                            file_path, instruction = self._extract_file_and_instruction(command)
                            if file_path and instruction:
                                success = await self.apply_code_edit(file_path, instruction)
                                response = "Kód módosítás sikeresen végrehajtva." if success else "Hiba a kód módosítása során."
                            else:
                                response = "Érvénytelen kódmódosítási parancs."
                        else:
                            # Process as generic code
                            response = command[command.find(":")+1:].strip()
                            
                    elif category == "REPLAY":
                        try:
                            index = int(command.split(":")[1].strip())
                            response = await self.handle_replay(index)
                        except (IndexError, ValueError):
                            response = "Érvénytelen REPLAY formátum."
                            
                    else:
                        # Try to process using OpenAI directly instead of websocket when possible
                        if self.openai_client:
                            # Try to extract the actual query from the command
                            query = command
                            if ":" in command:
                                query = command[command.find(":")+1:].strip()
                                
                            # First check cache
                            cached_response = self._get_from_cache(query)
                            if cached_response:
                                response = cached_response
                            else:
                                # If not in cache, decide whether to use WebSocket or direct API
                                if len(query) < 500:  # Short queries can go directly to OpenAI
                                    response = await self._send_openai_request(query)
                                else:  # Longer queries through WebSocket
                                    response = await self.send_command_to_websocket(command)
                        else:
                            # Fall back to WebSocket if no OpenAI client
                            response = await self.send_command_to_websocket(command)

                except Exception as e:
                    log_msg = f"[CRITICAL] {datetime.now()} Error processing command '{command[:60]}...': {str(e)}"
                    print(log_msg)
                    self.command_stats["errors"] += 1
                    
                    try:
                        os.makedirs("logs", exist_oké=True)  # Ensure logs directory exists
                        with open("logs/critical.log", "a", encoding="utf-8") as f:
                            f.write(log_msg + "\n")
                    except Exception as log_e:
                        print(f"[CRITICAL] FAILED TO WRITE TO LOG FILE: {log_e}")
                        
                    response = f"Kritikus hiba a parancs feldolgozása közben: {str(e)}"

                # Process the response if we have one
                if response:
                    # Special case for system commands already handled
                    is_handled_system_cmd = (
                        category == "ECHO" and 
                        command.startswith("CMD:") and 
                        self._is_system_command(command[command.find(":")+1:].strip())
                    )
                    
                    if not is_handled_system_cmd:
                        self.handle_response(response, original_command=command)
                        self._add_to_history(command)
                        self.log_command(command, response)
                else:
                    logger.info("No response generated for command.")

            except Exception as e:
                log_msg = f"[CRITICAL] {datetime.now()} Error in monitoring loop: {str(e)}"
                print(log_msg)
                self.command_stats["errors"] += 1
                
                try:
                    with open("logs/critical.log", "a", encoding="utf-8") as f:
                        f.write(log_msg + "\n")
                except:
                    pass
                    
                # Don't crash the loop, just continue
                await asyncio.sleep(1)
                
            # Only save cache periodically to reduce disk I/O
            if self.command_stats["total_commands"] % 20 == 0:
                self._save_cache()
    
    async def _process_json_command(self, json_text):
        """Process a JSON command."""
        try:
            # Clean the text - remove CMD: prefix if present
            if json_text.startswith("CMD:"):
                json_text = json_text[4:].trip()
                
            # Parse the JSON
            data = json.loads(json_text)
            
            # Check if this is a special command format
            if isinstance(data, dict):
                # Return a confirmation
                return f"JSON adat feldolgozva: {len(data)} mező"
            else:
                return f"JSON adat feldolgozva: {type(data).__name__}"
                
        except json.JSONDecodeError:
            return f"Érvénytelen JSON formátum"
        except Exception as e:
            return f"Hiba a JSON feldolgozása közben: {str(e)}"

    def close(self):
        """Clean up resources"""
        try:
            self.driver.quit()
            logger.info("Browser closed")
        except:
            pass

    def get_previous_command(self, index):
        """Get a previously executed command by index (1-based)"""
        try:
            # Convert to 0-based index
            actual_index = index - 1
            if 0 <= actual_index < len(self.command_history):
                return self.command_history[actual_index]
            return None
        except Exception as e:
            logger.error(f"Error getting previous command: {e}")
            return None

    def _reconnect_browser(self):
        """Újracsatlakozik a böngészőhöz érvénytelen munkamenet esetén"""
        try:
            logger.info("Attempting to reconnect to browser...")
            
            # Close the old driver if it exists
            try:
                if hasattr(self, 'driver'):
                    self.driver.quit()
            except:
                pass  # Ignore errors on closing
                
            # Wait a moment before reconnecting
            time.sleep(2)
            
            # Try to reconnect
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            
            service = Service(executable_path=self.chrome_driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            logger.info(f"Successfully reconnected to browser: {self.driver.title}")
            
            # Refresh the page if needed to ensure everything is working
            try:
                self.driver.refresh()
                time.sleep(2)  # Wait for page to reload
                logger.info("Browser page refreshed")
            except:
                logger.warning("Could not refresh browser page")
                
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            # If reconnection fails, try to launch a new browser instance
            try:
                logger.info("Attempting to launch a new browser instance...")
                self._launch_new_browser()
            except Exception as e2:
                logger.error(f"Failed to launch new browser: {e2}")
                # Create a critical error log
                with open("logs/critical.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] CRITICAL: Browser reconnection completely failed. Manual restart required.\n")


if __name__ == "__main__":
    # Configuration
    CHROME_PATH = r"C:\S\chatgpt_selenium_automation\chrome-win64\chrome.exe"
    CHROME_DRIVER_PATH = r"C:\S\chatgpt_selenium_automation\chromedriver-win64\chromedriver.exe"
    
    # Initialize and start the handler
    handler = AICommandHandler(CHROME_PATH, CHROME_DRIVER_PATH)
    
    try:
        # Aszinkron függvény futtatása az asyncio event loop-pal
        asyncio.run(handler.start_monitoring())
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    finally:
        handler.close()