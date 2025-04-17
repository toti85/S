import logging
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dom_analyzer.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("DOM_Analyzer")

class DOMAnalyzer:
    """
    Tool for analyzing DOM structures in AI interfaces (ChatGPT, Copilot) to 
    help debug command detection issues.
    """
    
    def __init__(self, chrome_driver_path, debug_port=9222):
        self.chrome_driver_path = chrome_driver_path
        self.debug_port = debug_port
        self.driver = self._setup_driver()
        
        # Command prefixes we're looking for
        self.command_prefixes = ("CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:")
        
    def _setup_driver(self):
        """Set up WebDriver connection to existing Chrome instance"""
        try:
            logger.info(f"Setting up connection to Chrome on port {self.debug_port}")
            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
            service = Service(self.chrome_driver_path)
            
            driver = webdriver.Chrome(service=service, options=options)
            logger.info(f"Connected to: {driver.title}")
            return driver
        except Exception as e:
            logger.error(f"Failed to connect to Chrome: {e}")
            raise
    
    def analyze_dom(self):
        """
        Analyze the DOM for command structures and output detailed information
        about potential command containers.
        """
        logger.info("Analyzing DOM for command structures...")
        
        # Strategy 1: Analyze assistant role messages in ChatGPT
        self.analyze_assistant_role_elements()
        
        # Strategy 2: Analyze text-base class elements (Copilot)
        self.analyze_text_base_elements()
        
        # Strategy 3: Analyze markdown and prose elements
        self.analyze_markdown_elements()
        
        # Strategy 4: Generic text content scan
        self.find_text_containing_commands()
        
        # Strategy 5: Dump essential DOM structure
        self.dump_dom_structure()
    
    def analyze_assistant_role_elements(self):
        """Analyze assistant role message elements in ChatGPT"""
        logger.info("Scanning for assistant role elements...")
        
        elements = self.driver.find_elements(By.CSS_SELECTOR, "div[data-message-author-role='assistant']")
        
        if not elements:
            logger.info("No assistant role elements found.")
            return
        
        logger.info(f"Found {len(elements)} assistant role elements")
        
        # Analyze the last few elements (more likely to contain recent commands)
        for i, el in enumerate(elements[-5:]):
            logger.info(f"Assistant element #{len(elements) - 5 + i + 1}:")
            
            # Check for markdown content
            markdown_divs = el.find_elements(By.CSS_SELECTOR, "div.markdown")
            if markdown_divs:
                for j, md in enumerate(markdown_divs):
                    text = md.text.strip()
                    logger.info(f"  Markdown #{j+1}: {text[:100]}...")
                    
                    # Check if this contains a command
                    if any(text.startswith(prefix) for prefix in self.command_prefixes):
                        logger.info(f"  ✅ COMMAND FOUND: {text[:150]}...")
            else:
                # If no markdown divs, check the text directly
                text = el.text.strip()
                logger.info(f"  Text: {text[:100]}...")
                
                if any(text.startswith(prefix) for prefix in self.command_prefixes):
                    logger.info(f"  ✅ COMMAND FOUND: {text[:150]}...")
    
    def analyze_text_base_elements(self):
        """Analyze text-base class elements (commonly used in Copilot)"""
        logger.info("Scanning for text-base elements...")
        
        elements = self.driver.find_elements(By.CSS_SELECTOR, "div.text-base")
        
        if not elements:
            logger.info("No text-base elements found.")
            return
        
        logger.info(f"Found {len(elements)} text-base elements")
        
        # Analyze the last few elements
        for i, el in enumerate(elements[-5:]):
            text = el.text.strip()
            logger.info(f"Text-base element #{len(elements) - 5 + i + 1}: {text[:100]}...")
            
            if any(text.startswith(prefix) for prefix in self.command_prefixes):
                logger.info(f"  ✅ COMMAND FOUND: {text[:150]}...")
    
    def analyze_markdown_elements(self):
        """Analyze generic markdown and prose elements"""
        logger.info("Scanning for markdown/prose elements...")
        
        elements = self.driver.find_elements(By.CSS_SELECTOR, ".markdown, .prose")
        
        if not elements:
            logger.info("No markdown/prose elements found.")
            return
        
        logger.info(f"Found {len(elements)} markdown/prose elements")
        
        # Analyze the last few elements
        for i, el in enumerate(elements[-5:]):
            text = el.text.strip()
            logger.info(f"Markdown/prose element #{len(elements) - 5 + i + 1}: {text[:100]}...")
            
            if any(text.startswith(prefix) for prefix in self.command_prefixes):
                logger.info(f"  ✅ COMMAND FOUND: {text[:150]}...")
    
    def find_text_containing_commands(self):
        """Find any text elements containing command prefixes"""
        logger.info("Scanning all text elements for command prefixes...")
        
        # Use JavaScript to find all elements with text content
        script = """
        const prefixes = ["CMD:", "CODE:", "INFO:", "FILE:", "REPLAY:"];
        const results = [];
        
        function scanElementsForCommands(elements) {
            for (const element of elements) {
                const text = element.textContent.trim();
                for (const prefix of prefixes) {
                    if (text.startsWith(prefix)) {
                        // Get element info
                        const classNames = element.className;
                        const tagName = element.tagName;
                        const id = element.id;
                        
                        results.push({
                            text: text.substring(0, 150),
                            prefix: prefix,
                            tagName: tagName,
                            className: classNames,
                            id: id
                        });
                        break;
                    }
                }
            }
        }
        
        // Scan all text-containing elements
        scanElementsForCommands(document.querySelectorAll('div, p, span, pre'));
        
        return results;
        """
        
        results = self.driver.execute_script(script)
        
        if not results:
            logger.info("No command text found in any elements.")
            return
        
        logger.info(f"Found {len(results)} elements containing command text:")
        for i, result in enumerate(results):
            logger.info(f"Command element #{i+1}:")
            logger.info(f"  Prefix: {result.get('prefix')}")
            logger.info(f"  Tag: {result.get('tagName')}")
            logger.info(f"  Class: {result.get('className')}")
            logger.info(f"  ID: {result.get('id')}")
            logger.info(f"  Text: {result.get('text')}...")
    
    def dump_dom_structure(self):
        """
        Dump the key DOM structure to help with debugging and
        understanding the current page structure
        """
        logger.info("Dumping essential DOM structure...")
        
        # Use JavaScript to get a simplified DOM structure
        script = """
        function getSimplifiedElement(el, depth = 0, maxDepth = 3) {
            if (depth > maxDepth || !el) return null;
            
            let children = [];
            if (el.children && depth < maxDepth) {
                for (let i = 0; i < el.children.length; i++) {
                    let child = getSimplifiedElement(el.children[i], depth + 1, maxDepth);
                    if (child) children.push(child);
                }
            }
            
            let text = '';
            if (el.textContent && el.children.length === 0) {
                text = el.textContent.trim().substring(0, 50);
            }
            
            return {
                tag: el.tagName,
                class: el.className,
                id: el.id,
                role: el.getAttribute('role') || el.getAttribute('data-message-author-role'),
                text: text ? text + (el.textContent.length > 50 ? '...' : '') : undefined,
                children: children.length > 0 ? children : undefined
            };
        }
        
        // Get chat container or main content
        const chatContainer = document.querySelector('main') || document.body;
        return getSimplifiedElement(chatContainer, 0, 2);
        """
        
        structure = self.driver.execute_script(script)
        
        if structure:
            logger.info("DOM Structure Summary:")
            logger.info(json.dumps(structure, indent=2))
        else:
            logger.info("Couldn't generate DOM structure")

    def close(self):
        """Close the browser connection"""
        try:
            self.driver.quit()
            logger.info("Browser connection closed")
        except:
            pass

def main():
    CHROME_DRIVER_PATH = r"C:\S\chatgpt_selenium_automation\chromedriver-win64\chromedriver.exe"
    
    analyzer = DOMAnalyzer(CHROME_DRIVER_PATH)
    try:
        analyzer.analyze_dom()
    except Exception as e:
        logger.error(f"Error during DOM analysis: {e}")
    finally:
        input("Press Enter to close...")
        analyzer.close()

if __name__ == "__main__":
    main()
