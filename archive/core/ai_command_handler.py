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
from replay.replay_manager import ReplayManager  # Helyesbített import útvonal  # Import the new ReplayManager
from openai import OpenAI  # Add OpenAI import
import pathlib  # For path handling
import json  # For config handling
import re  # For regex handling

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
        cmd_content = command[4:].strip()
        
        # Echo parancs kezelése
        if cmd_content.lower().startswith("echo"):
            return cmd_content[5:].strip()
            
        # További egyszerű parancsok implementálása...
        # TODO: Több parancs hozzáadása szükség szerint
        
        return f"Simple command executed: {cmd_content}"

    def start_monitoring(self):
        """Start the monitoring loop to detect and process commands"""
        logger.info("Starting AI command monitoring...")

        # Initialize WebSocket retry counter
        ws_retry_count = 0
        max_ws_retries = 10
        ws_retry_delay = 1

        while True:
            try:
                # Detect any commands in the DOM
                command = self.detect_commands()
                now = time.time()

                if command:  # Command already validated in detect_commands
                    logger.info(f"New command detected: {command[:50]}...")
                    response = ""

                    # Update tracking variables immediately
                    self.last_command = command
                    self.last_timestamp = now

                    try:
                        # 1. Először ellenőrizzük az egyszerű CMD: parancsokat
                        if self._is_simple_command(command):
                            response = self._handle_simple_command(command)
                            self._add_to_history(command)
                            if response:
                                self.send_response_via_selenium(response)
                            self.log_command(command, response)
                            continue

                        # 2. Ellenőrizzük a REPLAY parancsokat
                        if command.startswith("REPLAY:"):
                            try:
                                index = int(command.split(":")[1].strip())
                                previous_command = self.get_previous_command(index)

                                if previous_command:
                                    logger.info(f"Replaying command #{index}: {previous_command}")
                                    response = asyncio.run(self.send_command_to_websocket(previous_command))
                                else:
                                    response = f"Nincs elérhető REPLAY:{index} parancs"
                            except ValueError:
                                response = "Érvénytelen REPLAY formátum. Használat: REPLAY:X ahol X egy szám."

                        # 3. Időzített parancsok kezelése
                        elif self.is_scheduled_command(command):
                            # Csak akkor használjuk az OpenAI API-t, ha nem CMD: vagy CODE: prefix-szel kezdődik
                            if not command.startswith(("CMD:", "CODE:")):
                                file_path, instruction = self._extract_file_and_instruction(command)
                                delay_seconds = self.extract_schedule_delay(command)
                                if file_path and instruction and delay_seconds > 0:
                                    logger.info(f"Scheduling command for {file_path} with delay of {delay_seconds} seconds.")
                                    threading.Thread(target=self.schedule_delayed_command, 
                                                  args=(file_path, instruction, delay_seconds)).start()
                                    response = f"Parancs ütemezve: {delay_seconds} másodperc múlva végrehajtva."
                            else:
                                # Egyszerű időzített parancs, nem kell OpenAI
                                delay_seconds = self.extract_schedule_delay(command)
                                if delay_seconds > 0:
                                    threading.Thread(target=lambda: time.sleep(delay_seconds) or 
                                        self.send_response_via_selenium(f"Időzített parancs végrehajtva: {command}")).start()
                                    response = f"Egyszerű parancs ütemezve: {delay_seconds} másodperc múlva."

                        # 4. Kódszerkesztési parancsok kezelése
                        elif self._is_code_edit_command(command):
                            file_path, instruction = self._extract_file_and_instruction(command)
                            if file_path and instruction:
                                logger.info(f"Processing code edit command for {file_path}")
                                try:
                                    success = asyncio.run(self.apply_code_edit(file_path, instruction))
                                    response = "Kód módosítás sikeresen végrehajtva." if success else "Hiba a kód módosítása során."
                                except Exception as e:
                                    logger.error(f"Error during code edit: {e}")
                                    response = f"Hiba történt a kód módosítása során: {str(e)}"
                            else:
                                response = "Érvénytelen kód módosítási parancs: hiányzó fájl vagy utasítás."

                        # 5. Egyéb parancsok küldése WebSocketen keresztül
                        else:
                            response = asyncio.run(self.send_command_to_websocket(command))
                            if response and len(response.strip()) > 0:
                                self._add_to_history(command)

                        # Handle response
                        if response and len(response.strip()) > 0:
                            # Reset WebSocket retry counter on successful communication
                            ws_retry_count = 0
                            ws_retry_delay = 1

                            # Send response to ChatGPT
                            self.send_response_via_selenium(response)
                        else:
                            logger.warning("Empty response received, skipping submission")

                    except Exception as e:
                        ws_retry_count += 1
                        logger.error(f"Command execution failed (attempt {ws_retry_count}): {e}")

                        if ws_retry_count >= max_ws_retries:
                            logger.error("Max WebSocket retries reached, restarting monitoring...")
                            ws_retry_count = 0
                            ws_retry_delay = 1
                            continue

                        # Exponential backoff for WebSocket retries
                        ws_retry_delay *= 2
                        time.sleep(ws_retry_delay)
                        continue

                    # Log the command and response
                    self.log_command(command, response)

                # Sleep to prevent high CPU usage
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)  # Longer sleep on error
    
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


if __name__ == "__main__":
    # Configuration
    CHROME_PATH = r"C:\S\chatgpt_selenium_automation\chrome-win64\chrome.exe"
    CHROME_DRIVER_PATH = r"C:\S\chatgpt_selenium_automation\chromedriver-win64\chromedriver.exe"
    
    # Initialize and start the handler
    handler = AICommandHandler(CHROME_PATH, CHROME_DRIVER_PATH)
    
    try:
        handler.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    finally:
        handler.close()