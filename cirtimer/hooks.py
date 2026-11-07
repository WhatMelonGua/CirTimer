"""External actions fired on phase start / end (open URL, open file, run program).

Everything is logged to ``<data>/hooks.log`` because a hook that fails silently
is indistinguishable from a hook that never ran. Failures are also pushed to a
listener so the UI can show a notification.

Opening a target follows Windows' own rules:

* MSIX / Store apps (Notepad on Win11) must be *activated* by the shell —
  starting their exe directly opens nothing.
* Normal Win32 apps are started from the resolved default executable.
* When CirClock itself runs elevated, every child inherits that token, which is
  what breaks browsers ("已有实例以提升的权限运行") and packaged apps. The only
  real fix is to run CirClock unelevated; the launcher falls back to the shell
  and :func:`diagnose` reports the situation.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from . import assoc
from .config import Hook, data_dir, project_root

LOG: list[str] = []
_listener: Callable[[bool, str], None] | None = None
LOG_FILE = "hooks.log"
LOG_LIMIT = 256 * 1024

URL_SCHEMES = ("http://", "https://", "ftp://", "mailto:", "file://")


def set_listener(fn: Callable[[bool, str], None] | None) -> None:
    global _listener
    _listener = fn


def log_path() -> Path:
    return data_dir() / LOG_FILE


def _rotate() -> None:
    path = log_path()
    try:
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.replace(path.with_suffix(".old.log"))
    except OSError:
        pass


def _record(ok: bool, message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {'OK  ' if ok else 'FAIL'} {message}"
    LOG.append(line)
    if len(LOG) > 200:
        del LOG[:-200]
    try:
        _rotate()
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    if not ok and _listener is not None:
        try:
            _listener(ok, message)
        except Exception:
            pass


def is_elevated() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _resolve(target: str) -> Path | None:
    """Relative file targets are resolved against the project root, not the cwd."""
    path = Path(target).expanduser()
    if path.is_absolute():
        return path
    return (project_root() / path).resolve()


# ---------------------------------------------------------------- launchers ---
def _startfile(target: str) -> bool:
    """Canonical shell activation — the only way packaged apps get launched."""
    if sys.platform == "win32":
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.Popen([opener, target], close_fds=True)
        return True
    except Exception:
        return False


def _open_via_shell(target: str) -> bool:
    """Last resort: ask the desktop shell to open it (Windows only)."""
    if sys.platform != "win32":
        return False
    explorer = Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
    try:
        subprocess.Popen([str(explorer), target], close_fds=True)
        return True
    except Exception:
        return False


def _launch_local(target: str) -> tuple[bool, str]:
    """Start the resolved default executable directly (Win32 apps only)."""
    resolved = assoc.open_command(target)
    if not resolved:
        return False, ""
    exe, args = resolved
    try:
        subprocess.Popen([exe, *args], close_fds=True)
        return True, f"默认应用 {Path(exe).name}"
    except Exception as exc:
        return False, str(exc)


def _open_target(target: str) -> tuple[bool, str]:
    """Open *target* exactly like double-clicking it would.

    ``os.startfile`` is the shell's own "open with the default app" call
    (ShellExecute under the hood) and is the only thing that can activate MSIX
    apps such as Notepad, so it always goes first. The rest are fallbacks for
    the rare case where the shell refuses.
    """
    elevated = is_elevated()
    progid = assoc.progid_for(target)
    label = Path(progid).name if progid else "系统默认"

    if _startfile(target):
        suffix = "（管理员模式）" if elevated else ""
        return True, f"系统默认程序 {label}{suffix}"

    ok, detail = _launch_local(target)
    if ok:
        return True, detail

    if _open_via_shell(target):
        return True, "资源管理器" + ("（管理员模式）" if elevated else "")

    # stdlib webbrowser also walks its own browser list after startfile fails
    if target.lower().startswith(URL_SCHEMES):
        try:
            import webbrowser
            if webbrowser.open(target):
                return True, "webbrowser 兜底"
        except Exception:
            pass
        return False, "系统默认程序、直接启动、资源管理器、webbrowser 都没成功"

    return False, "系统默认程序和直接启动都没有成功"


# ------------------------------------------------------------------- report ---
def diagnose(targets: list[str]) -> str:
    """Human-readable report: elevation, association chain, recent hook runs."""
    canary = ("是（浏览器会提示“已有实例以提升的权限运行”，商店应用可能打不开）"
              if is_elevated() else "否")
    lines = [f"管理员模式：{canary}", f"数据目录：{data_dir()}", ""]
    for target in targets:
        progid = assoc.progid_for(target)
        command = assoc.raw_command(progid) if progid else None
        resolved = assoc.open_command(target)
        activation = assoc.needs_activation(progid, command)
        if activation:
            route = "os.startfile（打包应用只能靠系统激活）"
        elif is_elevated():
            route = "os.startfile（当前是管理员模式，可能被拦）"
        else:
            route = "os.startfile，失败再直接启动 exe"
        lines.append(target)
        lines.append(f"    来源     : {assoc.origin(target)}")
        lines.append(f"    用户选择 : {progid or '（没有 UserChoice）'}"
                     + (f"  ← 你上次点选的默认程序" if progid else ""))
        class_id = assoc.class_progid(target)
        if class_id and class_id != progid:
            lines.append(f"    类默认   : {class_id}（被 UserChoice 覆盖）")
        lines.append(f"    系统命令 : {command or '（没有注册命令）'}")
        lines.append(f"    需要激活 : {'是' if activation else '否'}")
        lines.append(f"    实际方式 : {route}")
        lines.append("")
    log = log_path()
    if log.is_file():
        tail = log.read_text(encoding="utf-8").strip().splitlines()[-8:]
        if tail:
            lines.append("最近执行记录：")
            lines.extend("    " + line for line in tail)
    return "\n".join(lines)


# --------------------------------------------------------------------- run ---
def run_one(hook: Hook) -> bool:
    target = (hook.target or "").strip()
    if not hook.enabled:
        return True
    if not target:
        _record(False, "动作没有填目标，已跳过")
        return False

    if hook.type == "run":
        program = _resolve(target)
        if program is None or not program.is_file():
            _record(False, f"程序不存在：{target}")
            return False
        args = shlex.split(hook.args, posix=False) if hook.args.strip() else []
        cwd = hook.cwd or str(program.parent)
        if cwd and not Path(cwd).is_dir():
            cwd = str(program.parent)
        try:
            subprocess.Popen([str(program), *args], cwd=cwd, close_fds=True)
            _record(True, f"运行 {program} {' '.join(args)}".strip())
            return True
        except Exception as exc:
            _record(False, f"运行失败 {program}：{exc}")
            return False

    # explicit program for this hook: beats the system default
    if (hook.program or "").strip():
        program = _resolve(hook.program)
        if program is None or not program.is_file():
            _record(False, f"指定程序不存在：{hook.program}")
            return False
        if target.lower().startswith(URL_SCHEMES):
            path = target
        else:
            resolved_target = _resolve(target)
            if resolved_target is None or not resolved_target.exists():
                _record(False, f"文件不存在：{target}")
                return False
            path = str(resolved_target)
        args = shlex.split(hook.args, posix=False) if hook.args.strip() else []
        try:
            subprocess.Popen([str(program), *args, path], close_fds=True)
            _record(True, f"用 {program.name} 打开 {path}")
            return True
        except Exception as exc:
            _record(False, f"用 {program.name} 打开失败：{exc}")
            return False

    if target.lower().startswith(URL_SCHEMES):
        ok, how = _open_target(target)
        _record(ok, f"打开链接 {target}（{how}）" if ok else f"打开链接失败 {target}：{how}")
        return ok

    path = _resolve(target)
    if path is None or not path.exists():
        _record(False, f"文件不存在：{target}")
        return False
    ok, how = _open_target(str(path))
    _record(ok, f"打开文件 {path}（{how}）" if ok else f"打开文件失败 {path}：{how}")
    return ok


def run_all(hooks: list[Hook] | None) -> list[bool]:
    return [run_one(hook) for hook in (hooks or [])]
