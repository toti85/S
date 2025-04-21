import json
import re

def route_response(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        return "ERROR"
    
    response = response.strip()
    
    # Ellenőrzés, hogy a parancs tartalmaz-e JSON-t (CMD: echo {...} és FORCE: prefixek kezelése)
    if response.startswith(("CMD:", "ECHO:")):
        # Ellenőrizzük, hogy van-e JSON tartalom a parancsban
        prefix_end = response.find(':') + 1
        cmd_content = response[prefix_end:].strip()
        
        # FORCE: prefix kezelése
        if cmd_content.startswith("FORCE:"):
            cmd_content = cmd_content[6:].strip()  # Eltávolítjuk a FORCE: prefixet
        
        # Ha a parancs tartalma JSON formátumú
        if ((cmd_content.startswith('{') and cmd_content.endswith('}')) or 
            (cmd_content.startswith('[') and cmd_content.endswith(']'))):
            try:
                json.loads(cmd_content)
                return "JSON"  # Ez egy JSON parancs
            except Exception:
                pass
        
        # Ha a parancs echo-val kezdődik és json-t tartalmaz
        if cmd_content.startswith("echo") and ("{" in cmd_content and "}" in cmd_content) or ("[" in cmd_content and "]" in cmd_content):
            # Próbáljuk kinyerni a JSON-t az echo parancsból
            try:
                # Próbáljuk megtalálni a JSON kezdetét (kapcsos vagy szögletes zárójelben)
                json_start = min([p for p in [cmd_content.find('{'), cmd_content.find('[')] if p >= 0], default=-1)
                if json_start >= 0:
                    json_content = cmd_content[json_start:]
                    json.loads(json_content)
                    return "JSON"
            except Exception:
                pass
    
    # ERROR
    if re.match(r"(?i)^(error|hiba|exception|failed|sikertelen)[:\s]", response):
        return "ERROR"
        
    # ECHO (csak ha nem JSON)
    if response.startswith(("CMD:", "INFO:", "ECHO:", "REPLAY:", "OUTPUT:", "RESPONSE:")):
        return "ECHO"
        
    # CODE
    if re.match(r"^def |^class |^import |^from |@\w|```", response) or 'python' in response[:20].lower():
        return "CODE"
        
    # JSON - közvetlen JSON tartalom
    if (response.startswith('{') and response.endswith('}')) or (response.startswith('[') and response.endswith(']')):
        try:
            json.loads(response)
            return "JSON"
        except Exception:
            pass
            
    return "UNKNOWN"