from __future__ import annotations

import ast
from pathlib import Path
import unittest


class AiogramDispatcherConfigurationTests(unittest.TestCase):
    def test_existing_dispatcher_uses_persistent_storage_and_event_isolation(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        dispatcher_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Dispatcher"
        ]
        self.assertEqual(len(dispatcher_calls), 1, "Only one existing Dispatcher should be configured")
        call = dispatcher_calls[0]
        keywords = {item.arg: item.value for item in call.keywords if item.arg}
        self.assertIn("storage", keywords)
        self.assertIn("events_isolation", keywords)
        self.assertIsInstance(keywords["storage"], ast.Call)
        self.assertEqual(keywords["storage"].func.id, "SQLiteFSMStorage")
        self.assertIsInstance(keywords["events_isolation"], ast.Call)
        self.assertEqual(keywords["events_isolation"].func.id, "SimpleEventIsolation")

    def test_dispatcher_cleanup_closes_fsm_middleware(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("await dp.fsm.close()", source)


if __name__ == "__main__":
    unittest.main()
