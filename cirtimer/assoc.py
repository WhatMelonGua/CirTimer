"""Resolve the *actual* default application for a file or URL, straight from the
registry, so hooks can launch a local executable instead of bouncing through the
shell.

Chain used by :func:`open_command`:
    HKCU\\...\\FileExts\\.ext\\UserChoice      -> ProgId   (what the user picked)
    HKCU\\...\\UrlAssociations\\https\\UserChoice -> ProgId
    HKCR\\<ProgId>\\shell\\open\\command        -> "C:\\...\\app.exe" "%1"

When the ProgId belongs to a packaged (Store/MSIX) app there is no local
executable to start: the app must be activated through the shell, and the caller
falls back to that. Everything here is read-only local registry access.
"""
from __future__ import annotations

from pathlib import Path

try:
    import winreg
except Exception:  # pragma: no cover - Windows only
    winreg = None  # type: ignore[assignment]

URL_SCHEMES = ("http://", "https://", "ftp://", "mailto:", "file://")

_SHELL_ACTIVATION = ("appsfolder", "applicationframehost")


def _query(root, path: str, name: str = "") -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return None


def _is_url(target: str) -> bool:
    return target.lower().startswith(URL_SCHEMES)


def class_progid(target: str) -> str | None:
    """The class-level ProgId (``HKCU\\Software\\Classes\\.ext``), no UserChoice."""
    if winreg is None or _is_url(target):
        return None
    ext = Path(target).suffix.lower()
    if not ext:
        return None
    return _query(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}", "") \
        or _query(winreg.HKEY_CLASSES_ROOT, ext, "")


def _ext_progid(ext: str) -> str | None:
    """ProgId for a file extension, UserChoice first, then the class default."""
    if winreg is None or not ext:
        return None
    base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
    found = _query(winreg.HKEY_CURRENT_USER, rf"{base}\{ext}\UserChoice", "ProgId")
    if found:
        return found
    return _query(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}", "") \
        or _query(winreg.HKEY_CLASSES_ROOT, ext, "")


HTML_EXTS = (".html", ".htm", ".xhtml")


def progid_for(target: str) -> str | None:
    """The ProgId Windows would use for this target, or None.

    URLs resolve through the scheme association first; when that is missing or
    broken (common after a browser update), the ``.html`` association is used
    instead — it belongs to the same browser and is almost always intact.
    """
    if winreg is None:
        return None
    if _is_url(target):
        scheme = target.split(":", 1)[0].lower()
        base = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations"
        found = _query(winreg.HKEY_CURRENT_USER, rf"{base}\{scheme}\UserChoice", "ProgId")
        if found:
            return found
        found = _query(winreg.HKEY_CLASSES_ROOT, scheme, "")
        if found:
            return found
        for ext in HTML_EXTS:
            found = _ext_progid(ext)
            if found:
                return found
        return None

    return _ext_progid(Path(target).suffix.lower())


def origin(target: str) -> str:
    """Where the ProgId came from — shown in the diagnostics report."""
    if _is_url(target):
        scheme = target.split(":", 1)[0].lower()
        base = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations"
        if _query(winreg.HKEY_CURRENT_USER, rf"{base}\{scheme}\UserChoice", "ProgId"):
            return f"协议 {scheme}（用户选择）"
        if _query(winreg.HKEY_CLASSES_ROOT, scheme, ""):
            return f"协议 {scheme}（类默认）"
        for ext in HTML_EXTS:
            if _ext_progid(ext):
                return f"网页关联 {ext}（协议关联缺失时的兜底）"
        return "没有找到"
    ext = Path(target).suffix.lower()
    base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
    if _query(winreg.HKEY_CURRENT_USER, rf"{base}\{ext}\UserChoice", "ProgId"):
        return f"扩展名 {ext}（用户选择）"
    if _ext_progid(ext):
        return f"扩展名 {ext}（类默认）"
    return "没有找到"


def raw_command(progid: str) -> str | None:
    if winreg is None or not progid:
        return None
    return _query(winreg.HKEY_CLASSES_ROOT, rf"{progid}\shell\open\command", "")


def is_packaged(progid: str | None, command: str | None) -> bool:
    """True only when there is no executable to start ourselves."""
    if not command:
        return True
    low = command.lower()
    if any(hint in low for hint in _SHELL_ACTIVATION):
        return True
    exe, _args = split_command(command)
    return not exe.lower().endswith(".exe")


def needs_activation(progid: str | None, command: str | None) -> bool:
    """True for MSIX / Store apps: they must be activated by the shell.

    Notepad on Win11 is such an app — its ProgId starts with ``AppX`` and its
    exe lives under ``WindowsApps``. Starting that exe directly often opens an
    empty window (or nothing), so the shell has to do the activation.
    """
    blob = f"{progid or ''} {command or ''}".lower()
    return ("appx" in blob or "windowsapps" in blob
            or any(hint in blob for hint in _SHELL_ACTIVATION))


def _argv_from_command_line(command: str) -> list[str] | None:
    """Split a Windows command line exactly like the shell does."""
    try:
        import ctypes

        argc = ctypes.c_int(0)
        ptr = ctypes.windll.shell32.CommandLineToArgvW(command, ctypes.byref(argc))
        if not ptr:
            return None
        try:
            return [ptr[i] for i in range(argc.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(ptr)
    except Exception:
        return None


def split_command(command: str) -> tuple[str, list[str]]:
    """Split a shell open command into executable + argument template."""
    command = command.strip()
    if not command:
        return "", []
    parts = _argv_from_command_line(command)
    if parts:
        return parts[0], parts[1:]
    # non-Windows fallback
    if command.startswith('"'):
        end = command.find('"', 1)
        exe = command[1:end] if end > 0 else command[1:]
        rest = command[end + 1:] if end > 0 else ""
    else:
        space = command.find(" ")
        exe = command if space < 0 else command[:space]
        rest = "" if space < 0 else command[space + 1:]
    return exe, [a.strip('"') for a in rest.split()]


def expand(args: list[str], target: str) -> list[str]:
    """Replace the %1 / %L / %* placeholders with the target."""
    out = []
    used = False
    for arg in args:
        if any(tok in arg for tok in ("%1", "%L", "%l", "%*")):
            out.append(arg.replace("%1", target).replace("%L", target)
                       .replace("%l", target).replace("%*", target))
            used = True
        else:
            out.append(arg)
    if not used:
        out.append(target)
    return out


def open_command(target: str) -> tuple[str, list[str]] | None:
    """A local executable + arguments that opens *target*, or None.

    None means "no local exe" — a pure shell activation — so the caller hands
    the target to the shell instead. The exe is not probed for existence: a
    missing file simply fails at launch time and the caller falls back.
    """
    progid = progid_for(target)
    command = raw_command(progid) if progid else None
    if not progid and not command:
        return None
    if is_packaged(progid, command):
        return None
    exe, args = split_command(command or "")
    if not exe:
        return None
    return exe, expand(args, target)
