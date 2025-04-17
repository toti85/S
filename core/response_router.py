import json
import re

def route_response(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        return "ERROR"
    response = response.strip()
    # ERROR
    if re.match(r"(?i)^(error|hiba|exception|failed|sikertelen)[:\s]", response):
        return "ERROR"
    # ECHO
    if response.startswith(("CMD:", "INFO:", "ECHO:", "REPLAY:", "OUTPUT:", "RESPONSE:")):
        return "ECHO"
    # CODE
    if re.match(r"^def |^class |^import |^from |@\w|```", response) or 'python' in response[:20].lower():
        return "CODE"
    # JSON
    if (response.startswith('{') and response.endswith('}')) or (response.startswith('[') and response.endswith(']')):
        try:
            json.loads(response)
            return "JSON"
        except Exception:
            pass
    return "UNKNOWN"