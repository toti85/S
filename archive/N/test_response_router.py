"""Unit tesztek a response_router modulhoz."""
import pytest
from response_router import route_response

def test_error_responses():
    """ERROR kategória tesztelése"""
    error_cases = [
        "Error: Something went wrong",
        "Hiba: Nem található a fájl",
        "Exception: Invalid argument",
        "Failed: Connection timeout",
        "Sikertelen: A művelet nem hajtható végre",
        "Traceback (most recent call last):\n  File 'test.py', line 42",
        "RuntimeError occurred while processing",
        "A critical error occurred in the system",
        None,  # None input should return ERROR
        42,    # Non-string input should return ERROR
    ]
    
    for case in error_cases:
        assert route_response(case) == "ERROR"

def test_json_responses():
    """JSON kategória tesztelése"""
    json_cases = [
        '{"name": "Test", "value": 42}',
        '[1, 2, 3, "test"]',
        '{\n  "complex": {\n    "nested": true\n  }\n}',
        '[ { "id": 1, "data": "test" } ]',
        '[true, false, null]',
        '{"special": "karakterek: őűáéúőű"}',
    ]
    
    for case in json_cases:
        assert route_response(case) == "JSON"

def test_code_responses():
    """CODE kategória tesztelése"""
    code_cases = [
        'def test_function():\n    pass',
        'class TestClass:\n    def __init__(self):\n        pass',
        '@decorator\ndef func(): pass',
        '```python\nprint("Hello")\n```',
        'import sys',
        'from os import path',
        '// JavaScript comment',
        '/* C-style comment */',
        '<?php echo "test"; ?>',
        'if condition:\n    do_something()',
        'async def coroutine():\n    await something()',
    ]
    
    for case in code_cases:
        assert route_response(case) == "CODE"

def test_echo_responses():
    """ECHO kategória tesztelése"""
    echo_cases = [
        'CMD: list files',
        'INFO: Processing complete',
        'ECHO: Hello World',
        'REPLAY: 42',
        'OUTPUT: Test result',
        'RESPONSE: Command executed',
    ]
    
    for case in echo_cases:
        assert route_response(case) == "ECHO"

def test_unknown_responses():
    """UNKNOWN kategória tesztelése"""
    unknown_cases = [
        'Plain text message',
        'Regular log entry',
        'Simple status update',
        '123456789',
        'Just some random text',
        '   spaces and tabs   ',
    ]
    
    for case in unknown_cases:
        assert route_response(case) == "UNKNOWN"

def test_edge_cases():
    """Szélsőséges esetek tesztelése"""
    edge_cases = {
        "": "ERROR",                    # Üres string
        "   ": "UNKNOWN",              # Csak whitespace
        "{}": "JSON",                  # Minimális JSON
        "[]": "JSON",                  # Üres JSON tömb
        "CMD:": "ECHO",               # Csak prefix
        "ERROR": "UNKNOWN",           # Nem prefix-szel kezdődő error
        "<!-- -->": "CODE",           # HTML komment
        "```": "UNKNOWN",             # Üres kódblokk jelölő
    }
    
    for case, expected in edge_cases.items():
        assert route_response(case) == expected

def test_mixed_content():
    """Kevert tartalmú válaszok tesztelése"""
    mixed_cases = {
        'Error in JSON: {"error": "test"}': "ERROR",  # Error prefix wins
        'CMD: {"json": true}': "ECHO",               # Echo prefix wins
        'def error_func(): raise Error': "CODE",     # Code pattern wins
        '```json\n{"test": true}\n```': "CODE",      # Code block wins over JSON
    }
    
    for case, expected in mixed_cases.items():
        assert route_response(case) == expected