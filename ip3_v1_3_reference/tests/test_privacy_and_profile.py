from __future__ import annotations
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.ip3.privacy import walk_forbidden_keys
from src.ip3.adaptive_profile import update_profile

class PrivacyAndProfileTests(unittest.TestCase):
    def test_forbidden_key_detected(self):
        key = "raw_" + "prompt"
        self.assertTrue(walk_forbidden_keys({key: "x"}))

    def test_digest_key_allowed(self):
        self.assertFalse(walk_forbidden_keys({"hostname_digest": "a"*64, "raw_prompt_recorded": False}))

    def test_profile_privacy_digest(self):
        p = update_profile(None, {"target": "central_server"})
        self.assertTrue(p.privacy_mode)
        self.assertEqual(len(p.profile_digest), 64)

if __name__ == "__main__": unittest.main()
