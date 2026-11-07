"""Hook routing: explicit program beats the system default; defaults resolve
through the registry."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DATA = ROOT / "data" / ".test"
TEST_DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CIRCLOCK_DATA", str(TEST_DATA))

from cirtimer import config, hooks  # noqa: E402


class HookProgramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[list[str]] = []

        def fake_popen(argv, **kwargs):
            self.calls.append(list(argv))
            return mock.MagicMock()

        self._patcher = mock.patch("cirtimer.hooks.subprocess.Popen", side_effect=fake_popen)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_explicit_program_receives_the_file(self) -> None:
        target = TEST_DATA / "demo_f1.txt"
        target.write_text("x", encoding="utf-8")
        hook = config.Hook(type="open", target=str(target), program=sys.executable)
        self.assertTrue(hooks.run_one(hook))
        self.assertEqual(self.calls[0][0], sys.executable)
        self.assertIn(str(target), " ".join(self.calls[0]))

    def test_explicit_program_with_extra_args(self) -> None:
        target = TEST_DATA / "demo_f2.txt"
        target.write_text("x", encoding="utf-8")
        hook = config.Hook(type="open", target=str(target), program=sys.executable,
                           args="--reuse-window")
        self.assertTrue(hooks.run_one(hook))
        self.assertIn("--reuse-window", self.calls[0])
        self.assertEqual(self.calls[0][-1], str(target))

    def test_missing_program_is_reported_not_launched(self) -> None:
        hook = config.Hook(type="open", target=str(TEST_DATA / "demo_f1.txt"),
                           program=str(ROOT / "nope.exe"))
        self.assertFalse(hooks.run_one(hook))
        self.assertEqual(self.calls, [])

    def test_missing_file_is_reported(self) -> None:
        hook = config.Hook(type="open", target=str(TEST_DATA / "not_there.txt"),
                           program=sys.executable)
        self.assertFalse(hooks.run_one(hook))
        self.assertEqual(self.calls, [])

    def test_program_field_round_trips(self) -> None:
        hook = config.Hook(type="open", target="x.txt", program=r"D:\Code.exe")
        restored = config.Hook.from_dict(hook.to_dict())
        self.assertEqual(restored.program, r"D:\Code.exe")

    def test_old_hook_without_program_still_parses(self) -> None:
        restored = config.Hook.from_dict({"type": "open", "target": "x.txt"})
        self.assertEqual(restored.program, "")


class LaunchOrderTests(unittest.TestCase):
    def test_startfile_is_preferred(self) -> None:
        calls = []
        with mock.patch("cirtimer.hooks._startfile", side_effect=lambda t: calls.append(t) or True), \
             mock.patch("cirtimer.hooks.subprocess.Popen") as popen:
            ok, how = hooks._open_target("https://example.com")
        self.assertTrue(ok)
        self.assertEqual(calls, ["https://example.com"])
        self.assertIn("系统默认程序", how)
        popen.assert_not_called()

    def test_falls_back_to_exe_when_startfile_fails(self) -> None:
        with mock.patch("cirtimer.hooks._startfile", return_value=False), \
             mock.patch("cirtimer.hooks._launch_local", return_value=(True, "默认应用 x.exe")):
            ok, how = hooks._open_target(str(TEST_DATA / "demo_f1.txt"))
        self.assertTrue(ok)
        self.assertIn("默认应用", how)

    def test_reports_failure_when_everything_fails(self) -> None:
        with mock.patch("cirtimer.hooks._startfile", return_value=False), \
             mock.patch("cirtimer.hooks._launch_local", return_value=(False, "")), \
             mock.patch("cirtimer.hooks._open_via_shell", return_value=False):
            ok, how = hooks._open_target(str(TEST_DATA / "demo_f1.txt"))
        self.assertFalse(ok)
        self.assertTrue(how)


class DiagnoseTests(unittest.TestCase):
    def test_report_mentions_user_choice_and_elevation(self) -> None:
        text = hooks.diagnose([str(TEST_DATA / "demo_f1.txt")])
        self.assertIn("管理员模式", text)
        self.assertIn("用户选择", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
