import unittest
from replay_manager import ReplayManager
import time

class TestReplayManager(unittest.TestCase):
    def setUp(self):
        self.manager = ReplayManager(max_history_size=5, max_retries=3, retry_cooldown=0.1)

    def test_add_and_get_command(self):
        # Test adding a command
        self.manager.add_command("CMD:test", "response", True)
        cmd = self.manager.get_command(1)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["command"], "CMD:test")
        self.assertEqual(cmd["response"], "response")
        self.assertTrue(cmd["success"])

    def test_history_size_limit(self):
        # Add more commands than the limit
        for i in range(7):
            self.manager.add_command(f"CMD:test{i}", "response", True)
        
        # Check that only max_history_size commands are kept
        self.assertEqual(len(self.manager.command_history), 5)
        # Verify the most recent commands are kept
        self.assertEqual(self.manager.get_command(1)["command"], "CMD:test6")

    def test_retry_logic(self):
        # Test failed command retry logic
        cmd = "CMD:fail_test"
        
        # First attempt
        self.manager.add_command(cmd, "error", False)
        self.assertTrue(self.manager.should_retry(cmd))
        
        # Second attempt
        self.manager.add_command(cmd, "error", False)
        self.assertTrue(self.manager.should_retry(cmd))
        
        # Third attempt
        self.manager.add_command(cmd, "error", False)
        self.assertFalse(self.manager.should_retry(cmd))

    def test_command_validation(self):
        # Test valid commands
        self.assertTrue(self.manager.validate_command("CMD:test"))
        self.assertTrue(self.manager.validate_command("CODE:print('test')"))
        self.assertTrue(self.manager.validate_command("INFO:status"))
        
        # Test invalid commands
        self.assertFalse(self.manager.validate_command(""))
        self.assertFalse(self.manager.validate_command("INVALID:test"))
        self.assertFalse(self.manager.validate_command("REPLAY:invalid"))

    def test_retry_cooldown(self):
        cmd = "CMD:cooldown_test"
        
        # Add failed command
        self.manager.add_command(cmd, "error", False)
        
        # Immediate retry should be blocked by cooldown
        self.assertFalse(self.manager.should_retry(cmd))
        
        # Wait for cooldown
        time.sleep(0.2)
        
        # Now retry should be allowed
        self.assertTrue(self.manager.should_retry(cmd))

if __name__ == '__main__':
    unittest.main()