"""Offline security regression tests for the fixed local job schema."""
import importlib.util
import json
from pathlib import Path
import unittest

AGENT_PATH = Path(__file__).resolve().parents[1] / "automation" / "pulse_local_agent.py"
SPEC = importlib.util.spec_from_file_location("pulse_local_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


def good(**patch):
    value = {
        "version": 1, "job_id": "lavoro-prezzi-pilot-001",
        "task": "rewrite_verified_editorial_drafts",
        "start": 1, "limit": 2, "enabled": False,
    }
    value.update(patch)
    return json.dumps(value).encode("utf-8")


class TestLocalAgentSafety(unittest.TestCase):
    def test_valid_job(self):
        d = agent.parse_job(good())
        self.assertEqual(d["start"], 1)
        self.assertFalse(d["enabled"])

    def test_no_arbitrary_commands(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good(command="powershell"))

    def test_only_fixed_operation(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good(task="run_any_script"))

    def test_boolean_is_not_integer(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good(start=True))

    def test_no_unbounded_range(self):
        for value in [good(start=5, limit=2), good(limit=3),
                      good(start=-1), good(start=6)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                agent.parse_job(value)

    def test_no_path_traversal(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good(job_id="../not-allowed"))

    def test_no_duplicate_keys(self):
        with self.assertRaises(ValueError):
            agent.parse_job(b'{"enabled":true,"enabled":false}')

    def test_explicit_boolean_only(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good(enabled=1))

    def test_no_oversized_job(self):
        with self.assertRaises(ValueError):
            agent.parse_job(good() + b" " * 4097)


if __name__ == "__main__":
    unittest.main()
