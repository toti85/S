import pytest
import asyncio
from replay_manager import ReplayManager
import time
import os

@pytest.fixture
def manager():
    return ReplayManager(max_history_size=5, max_retries=3, retry_cooldown=0.1)

@pytest.fixture
def command_log():
    # Létrehozunk egy ideiglenes command_log.txt fájlt teszteléshez
    with open("command_log.txt", "w", encoding="utf-8") as f:
        f.write("[2024-04-14 10:00:00] COMMAND: CMD:test_command\n")
        f.write("Response: Test response\n\n")
        f.write("[2024-04-14 10:01:00] COMMAND: CODE:print('hello')\n")
        f.write("Response: hello\n\n")
    yield
    # Töröljük a tesztfájlt
    if os.path.exists("command_log.txt"):
        os.remove("command_log.txt")

@pytest.mark.asyncio
async def test_replay_valid_command(manager, command_log):
    # Teszteljük létező parancs végrehajtását
    result = await manager.replay_command(1)
    assert "Test response" in result or "test_command" in result

@pytest.mark.asyncio
async def test_replay_nonexistent_command(manager, command_log):
    # Teszteljük nem létező ID esetén a hibakezelést
    result = await manager.replay_command(999)
    assert "Nem található 999 azonosítójú parancs" in result

@pytest.mark.asyncio
async def test_replay_cmd_type(manager, command_log):
    # Teszteljük CMD: típusú parancs végrehajtását
    result = await manager.replay_command(1)
    assert result is not None
    assert isinstance(result, str)

@pytest.mark.asyncio
async def test_replay_code_type(manager, command_log):
    # Teszteljük CODE: típusú parancs végrehajtását
    result = await manager.replay_command(2)
    assert result is not None
    assert isinstance(result, str)

# Megtartjuk a többi létező tesztfüggvényt is, de átalakítjuk pytest formátumra
def test_add_and_get_command(manager):
    manager.add_command("CMD:test", "response", True)
    cmd = manager.get_command(1)
    assert cmd is not None
    assert cmd["command"] == "CMD:test"
    assert cmd["response"] == "response"
    assert cmd["success"] is True

def test_history_size_limit(manager):
    for i in range(7):
        manager.add_command(f"CMD:test{i}", "response", True)
    
    assert len(manager.command_history) == 5
    assert manager.get_command(1)["command"] == "CMD:test6"

def test_retry_logic(manager):
    cmd = "CMD:fail_test"
    
    manager.add_command(cmd, "error", False)
    assert manager.should_retry(cmd) is True
    
    manager.add_command(cmd, "error", False)
    assert manager.should_retry(cmd) is True
    
    manager.add_command(cmd, "error", False)
    assert manager.should_retry(cmd) is False

def test_command_validation(manager):
    assert manager.validate_command("CMD:test") is True
    assert manager.validate_command("CODE:print('test')") is True
    assert manager.validate_command("INFO:status") is True
    
    assert manager.validate_command("") is False
    assert manager.validate_command("INVALID:test") is False
    assert manager.validate_command("REPLAY:invalid") is False

def test_retry_cooldown(manager):
    cmd = "CMD:cooldown_test"
    
    manager.add_command(cmd, "error", False)
    assert manager.should_retry(cmd) is False
    
    time.sleep(0.2)
    assert manager.should_retry(cmd) is True