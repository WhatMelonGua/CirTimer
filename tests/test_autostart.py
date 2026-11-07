"""Autostart registry logic, exercised against a fake winreg.

The real registry is not written during tests: HKCU writes are blocked in some
sandboxes, and a test suite must never touch the user's login items.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cirtimer import autostart  # noqa: E402


class _Key:
    def __init__(self, store: dict) -> None:
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    REG_SZ = 1

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        return _Key(self.store)

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key.store[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key.store:
            raise FileNotFoundError(name)
        del key.store[name]


class AutostartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeWinreg()
        self._real = autostart.winreg
        autostart.winreg = self.fake  # type: ignore[assignment]

    def tearDown(self) -> None:
        autostart.winreg = self._real  # type: ignore[assignment]

    def test_disabled_by_default(self) -> None:
        self.assertFalse(autostart.is_enabled())

    def test_enable_writes_pythonw_command(self) -> None:
        self.assertTrue(autostart.enable())
        self.assertTrue(autostart.is_enabled())
        value = self.fake.store["CirClock"]
        self.assertIn("pythonw.exe", value)
        self.assertIn("CirClock.pyw", value)
        self.assertTrue(value.startswith('"') and value.endswith('"'))

    def test_disable_removes_value(self) -> None:
        autostart.enable()
        self.assertTrue(autostart.disable())
        self.assertFalse(autostart.is_enabled())

    def test_disable_when_absent_is_ok(self) -> None:
        self.assertTrue(autostart.disable())
        self.assertFalse(autostart.is_enabled())

    def test_missing_winreg_is_graceful(self) -> None:
        autostart.winreg = None  # type: ignore[assignment]
        self.assertFalse(autostart.is_enabled())
        self.assertFalse(autostart.enable())
        self.assertFalse(autostart.disable())


if __name__ == "__main__":
    unittest.main(verbosity=2)
