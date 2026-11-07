"""Default-application resolution helpers (pure parsing, no registry access)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cirtimer import assoc  # noqa: E402


class SplitCommandTests(unittest.TestCase):
    def test_quoted_exe_with_placeholder(self) -> None:
        exe, args = assoc.split_command('"C:\\Apps\\Viewer.exe" --open "%1"')
        self.assertEqual(exe, r"C:\Apps\Viewer.exe")
        self.assertEqual(args, ["--open", "%1"])

    def test_unquoted_exe(self) -> None:
        exe, args = assoc.split_command(r"C:\Windows\notepad.exe %1")
        self.assertEqual(exe, r"C:\Windows\notepad.exe")
        self.assertEqual(args, ["%1"])

    def test_empty(self) -> None:
        self.assertEqual(assoc.split_command(""), ("", []))


class ExpandTests(unittest.TestCase):
    def test_percent_one_replaced_inside_quotes(self) -> None:
        args = assoc.expand(["--single-argument", "%1"], "https://example.com/a b")
        self.assertEqual(args, ["--single-argument", "https://example.com/a b"])

    def test_percent_l_and_star(self) -> None:
        self.assertEqual(assoc.expand(["%L"], "C:\\x.txt"), ["C:\\x.txt"])
        self.assertEqual(assoc.expand(["%*"], "C:\\x.txt"), ["C:\\x.txt"])

    def test_target_appended_when_no_placeholder(self) -> None:
        self.assertEqual(assoc.expand(["--flag"], "C:\\x.txt"), ["--flag", "C:\\x.txt"])


class PackagedTests(unittest.TestCase):
    def test_shell_activation_is_packaged(self) -> None:
        self.assertTrue(assoc.is_packaged("MSEdge", 'explorer.exe shell:AppsFolder\\MSEdge'))
        self.assertTrue(assoc.is_packaged("X", "ApplicationFrameHost.exe"))

    def test_windowsapps_notepad_is_local(self) -> None:
        cmd = ('"C:\\Program Files\\WindowsApps\\Microsoft.WindowsNotepad_11_x64__8wekyb3d8bbwe'
               '\\Notepad\\Notepad.exe" "%1"')
        self.assertFalse(assoc.is_packaged("AppX4ztfk9wxr86nxmzzq47px0nh0e58b8fw", cmd))

    def test_missing_command_is_packaged(self) -> None:
        self.assertTrue(assoc.is_packaged("Something", None))
        self.assertTrue(assoc.is_packaged("Something", ""))


class ProgidTests(unittest.TestCase):
    def test_url_scheme_lookup_does_not_crash(self) -> None:
        # value depends on the machine; only the code path is asserted
        value = assoc.progid_for("https://example.com")
        self.assertTrue(value is None or isinstance(value, str))

    def test_file_extension_lookup_does_not_crash(self) -> None:
        value = assoc.progid_for(r"C:\some\file.txt")
        self.assertTrue(value is None or isinstance(value, str))


if __name__ == "__main__":
    unittest.main(verbosity=2)
