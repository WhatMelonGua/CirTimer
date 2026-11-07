"""Dialogs: phase editor, hook editor, queue editor."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget)

from .. import actions as actions_mod
from .. import audio as audio_mod
from .. import config
from .icons import svg_pixmap
from .spinbox import DecimalBox, NumberBox

KIND_LABELS = [
    ("focus", "专注"),
    ("break", "休息"),
    ("move", "活动 / 走动"),
    ("stretch", "拉伸"),
    ("eye", "护眼"),
    ("water", "饮水"),
    ("custom", "自定义"),
]

ICON_PALETTE = ["🧑‍💻", "🚶", "🧘", "🦵", "🌿", "💧", "👁", "☕", "🛋", "🍅", "🧎", "🫁"]

COLOR_PALETTE = ["#2B6CF6", "#12B886", "#E8A33D", "#7C6CF6", "#E5484D",
                 "#1FA8C9", "#8E8E93", "#35D0A5"]


def _swatch(color: str, size: int = 16) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, 4, 4)
    p.end()
    return QIcon(pm)


def _dialog_card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    return card, lay


def _holder(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    return w


# ------------------------------------------------------------ hook editor ---
class HookDialog(QDialog):
    def __init__(self, hook: config.Hook | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("外部动作")
        self.setMinimumWidth(460)
        hook = hook or config.Hook()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.type_box = QComboBox()
        self.type_box.addItem("打开链接 / 文件（默认程序）", "open")
        self.type_box.addItem("运行程序（可带参数）", "run")
        idx = self.type_box.findData(hook.type)
        self.type_box.setCurrentIndex(max(0, idx))
        form.addRow("类型", self.type_box)

        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        self.target = QLineEdit(hook.target)
        self.target.setPlaceholderText("https://… 或 C:\\path\\file.pdf 或 program.exe")
        browse = QPushButton("浏览…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        target_row.addWidget(self.target, 1)
        target_row.addWidget(browse)
        form.addRow("目标", _holder(target_row))

        self.args = QLineEdit(hook.args)
        self.args.setPlaceholderText("仅运行程序时使用，例如 --fullscreen --mute")
        form.addRow("参数", self.args)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(6)
        self.program = QLineEdit(getattr(hook, "program", ""))
        self.program.setPlaceholderText("留空 = 用系统默认程序；也可以指定 Code.exe 之类")
        pick_prog = QPushButton("选择…")
        pick_prog.setObjectName("Ghost")
        pick_prog.clicked.connect(self._browse_program)
        prog_row.addWidget(self.program, 1)
        prog_row.addWidget(pick_prog)
        form.addRow("打开方式", _holder(prog_row))

        cwd_row = QHBoxLayout()
        cwd_row.setSpacing(6)
        self.cwd = QLineEdit(hook.cwd)
        self.cwd.setPlaceholderText("留空则用程序所在目录")
        pick = QPushButton("选择…")
        pick.setObjectName("Ghost")
        pick.clicked.connect(self._browse_dir)
        cwd_row.addWidget(self.cwd, 1)
        cwd_row.addWidget(pick)
        form.addRow("工作目录", _holder(cwd_row))

        self.enabled = QCheckBox("启用这条动作")
        self.enabled.setChecked(hook.enabled)
        form.addRow("", self.enabled)

        root.addLayout(form)

        hint = QLabel("「打开」走 Windows 文件关联：网址用浏览器、文档用默认程序，\n"
                      "和双击文件完全一样。「运行」则直接启动可执行文件。")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._update_enabled()
        self.type_box.currentIndexChanged.connect(self._update_enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _update_enabled(self) -> None:
        is_run = self.type_box.currentData() == "run"
        self.args.setEnabled(is_run)
        self.cwd.setEnabled(is_run)
        self.program.setEnabled(not is_run)

    def _browse_program(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择打开文件用的程序", "",
                                              "程序 (*.exe);;所有文件 (*.*)")
        if path:
            self.program.setText(str(Path(path)))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择文件或程序", "", "所有文件 (*.*)")
        if path:
            self.target.setText(str(Path(path)))

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择工作目录")
        if path:
            self.cwd.setText(str(Path(path)))

    def value(self) -> config.Hook:
        return config.Hook(type=self.type_box.currentData(), target=self.target.text().strip(),
                           program=self.program.text().strip(),
                           args=self.args.text().strip(), cwd=self.cwd.text().strip(),
                           enabled=self.enabled.isChecked())


# ----------------------------------------------------------- hook listing ---
class HookList(QWidget):
    def __init__(self, hooks: list[config.Hook], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hooks = [copy.deepcopy(h) for h in hooks]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.list = QListWidget()
        self.list.setMinimumHeight(64)
        self.list.itemDoubleClicked.connect(lambda _: self._edit())
        lay.addWidget(self.list, 1)

        col = QVBoxLayout()
        col.setSpacing(4)
        for text, slot in (("添加", self._add), ("编辑", self._edit), ("删除", self._remove)):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch()
        lay.addLayout(col)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        for hook in self._hooks:
            label = f"{'打开' if hook.type == 'open' else '运行'} · {hook.target}"
            if not hook.enabled:
                label += "（已禁用）"
            item = QListWidgetItem(label)
            item.setToolTip(hook.target)
            self.list.addItem(item)

    def _add(self) -> None:
        dlg = HookDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = dlg.value()
            if value.target:
                self._hooks.append(value)
                self._refresh()

    def _edit(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._hooks):
            dlg = HookDialog(self._hooks[row], self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._hooks[row] = dlg.value()
                self._refresh()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._hooks):
            del self._hooks[row]
            self._refresh()

    def hooks(self) -> list[config.Hook]:
        return [copy.deepcopy(h) for h in self._hooks]


# ---------------------------------------------------------- phase editor ---
class PhaseDialog(QDialog):
    def __init__(self, phase: config.Phase | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑阶段")
        self.setMinimumSize(620, 660)
        self._phase = copy.deepcopy(phase) if phase else config.Phase(name="新阶段", minutes=25)
        ph = self._phase

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # --- basics
        card, cl = _dialog_card()
        form = QFormLayout()
        form.setSpacing(8)
        self.name = QLineEdit(ph.name)
        form.addRow("名称", self.name)

        self.kind = QComboBox()
        for key, label in KIND_LABELS:
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(ph.kind)))
        form.addRow("类型", self.kind)

        dur_row = QHBoxLayout()
        dur_row.setSpacing(6)
        self.minutes = DecimalBox()
        self.minutes.setRange(0.5, 600)
        self.minutes.setDecimals(1)
        self.minutes.setSuffix(" 分钟")
        self.minutes.setValue(ph.minutes)
        self.use_range = QCheckBox("使用区间")
        self.use_range.setChecked(ph.use_range)
        self.range_min = DecimalBox()
        self.range_max = DecimalBox()
        for box, value in ((self.range_min, ph.minutes_min), (self.range_max, ph.minutes_max)):
            box.setRange(0.5, 600)
            box.setDecimals(1)
            box.setValue(value)
        sep = QLabel("—")
        dur_row.addWidget(self.minutes)
        dur_row.addWidget(self.use_range)
        dur_row.addWidget(self.range_min)
        dur_row.addWidget(sep)
        dur_row.addWidget(self.range_max)
        dur_row.addStretch()
        form.addRow("时长", _holder(dur_row))
        cl.addLayout(form)
        lay.addWidget(card)

        # --- look
        card, cl = _dialog_card()
        title = QLabel("外观")
        title.setObjectName("H2")
        cl.addWidget(title)
        look = QFormLayout()
        look.setSpacing(8)

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self.color_btn = QPushButton("选择颜色")
        self.color_btn.setObjectName("Ghost")
        self.color_btn.setIcon(_swatch(ph.color))
        self.color_btn.clicked.connect(self._pick_color)
        self.color_hex = QLineEdit(ph.color)
        self.color_hex.setFixedWidth(88)
        self.color_hex.editingFinished.connect(self._color_from_hex)
        color_row.addWidget(self.color_btn)
        color_row.addWidget(self.color_hex)
        for value in COLOR_PALETTE:
            b = QPushButton()
            b.setObjectName("Swatch")
            b.setFixedSize(22, 22)
            b.setIcon(_swatch(value, 18))
            b.setToolTip(value)
            b.clicked.connect(lambda _=False, v=value: self._set_color(v))
            color_row.addWidget(b)
        color_row.addStretch()
        look.addRow("颜色", _holder(color_row))

        self.icon = QLineEdit(ph.icon)
        self.icon.setPlaceholderText("emoji 或图片路径，可留空")
        self.icon.setMaximumWidth(240)
        icon_box = QVBoxLayout()
        icon_box.setSpacing(6)
        icon_box.addWidget(self.icon)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, emoji in enumerate(ICON_PALETTE):
            b = QPushButton(emoji)
            b.setObjectName("Emoji")
            b.setFixedSize(34, 30)
            b.setToolTip("点击填入图标")
            b.clicked.connect(lambda _=False, v=emoji: self.icon.setText(v))
            grid.addWidget(b, i // 8, i % 8)
        grid.setColumnStretch(8, 1)
        icon_box.addLayout(grid)
        look.addRow("图标", _holder(icon_box))

        sound_row = QHBoxLayout()
        sound_row.setSpacing(6)
        self.sound = QComboBox()
        self.sound.addItem("默认（按类型）", "")
        for wav in sorted(audio_mod.SOUND_DIR.glob("*.wav")):
            self.sound.addItem(wav.stem, str(wav))
        if ph.sound:
            self.sound.addItem(Path(ph.sound).stem, ph.sound)
            self.sound.setCurrentIndex(self.sound.count() - 1)
        browse = QPushButton("自定义…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._pick_sound)
        preview = QPushButton("试听")
        preview.setObjectName("Ghost")
        preview.clicked.connect(self._preview)
        sound_row.addWidget(self.sound, 1)
        sound_row.addWidget(browse)
        sound_row.addWidget(preview)
        look.addRow("铃声", _holder(sound_row))

        self.sound_status = QLabel("")
        self.sound_status.setObjectName("Faint")
        look.addRow("", self.sound_status)
        cl.addLayout(look)
        lay.addWidget(card)

        # --- message + behaviour
        card, cl = _dialog_card()
        title = QLabel("提示与行为")
        title.setObjectName("H2")
        cl.addWidget(title)

        self.message = QTextEdit(ph.message)
        self.message.setAcceptRichText(False)
        self.message.setPlaceholderText("到点时显示在提醒卡上的话，可留空")
        self.message.setFixedHeight(70)
        self.message.textChanged.connect(self._autogrow_message)
        cl.addWidget(self.message)

        flags = QHBoxLayout()
        flags.setSpacing(14)
        self.require_leave = QCheckBox("需要确认已离座")
        self.require_leave.setChecked(ph.require_leave)
        self.allow_skip = QCheckBox("允许跳过")
        self.allow_skip.setChecked(ph.allow_skip)
        flags.addWidget(self.require_leave)
        flags.addWidget(self.allow_skip)
        flags.addStretch()
        cl.addWidget(_holder(flags))

        pre_row = QHBoxLayout()
        pre_row.setSpacing(6)
        self.pre_alert = QCheckBox("提前预告")
        self.pre_alert.setChecked(ph.pre_alert)
        self.pre_min = NumberBox()
        self.pre_max = NumberBox()
        for box, value in ((self.pre_min, ph.pre_alert_min), (self.pre_max, ph.pre_alert_max)):
            box.setRange(5, 600)
            box.setSuffix(" 秒")
            box.setValue(value)
        pre_row.addWidget(self.pre_alert)
        pre_row.addWidget(self.pre_min)
        pre_row.addWidget(QLabel("~"))
        pre_row.addWidget(self.pre_max)
        pre_row.addWidget(QLabel("随机一次软提示"))
        pre_row.addStretch()
        cl.addWidget(_holder(pre_row))

        act_row = QHBoxLayout()
        act_row.setSpacing(6)
        self._actions = list(ph.actions)
        self.action_btn = QPushButton(self._action_label())
        self.action_btn.setObjectName("Ghost")
        self.action_btn.clicked.connect(self._pick_actions)
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(self._clear_actions)
        act_row.addWidget(self.action_btn)
        act_row.addWidget(clear_btn)
        act_row.addStretch()
        cl.addWidget(_holder(act_row))
        lay.addWidget(card)

        # --- hooks
        card, cl = _dialog_card()
        title = QLabel("外部动作（可留空）")
        title.setObjectName("H2")
        cl.addWidget(title)
        cl.addWidget(QLabel("阶段开始时"))
        self.hooks_start = HookList(ph.hooks_start)
        cl.addWidget(self.hooks_start)
        cl.addWidget(QLabel("阶段结束时"))
        self.hooks_end = HookList(ph.hooks_end)
        cl.addWidget(self.hooks_end)
        lay.addWidget(card)
        lay.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(18, 8, 18, 12)
        wl.addStretch()
        wl.addWidget(buttons)
        root.addWidget(wrap)

        self.use_range.toggled.connect(self._sync_range)
        self.pre_alert.toggled.connect(self._sync_pre)
        self._sync_range(ph.use_range)
        self._sync_pre(ph.pre_alert)
        self._autogrow_message()

    # -- small helpers
    def _sync_range(self, on: bool) -> None:
        self.minutes.setEnabled(not on)
        self.range_min.setEnabled(on)
        self.range_max.setEnabled(on)

    def _sync_pre(self, on: bool) -> None:
        self.pre_min.setEnabled(on)
        self.pre_max.setEnabled(on)

    def _autogrow_message(self) -> None:
        """Grow the message box with its content instead of clipping lines.

        QPlainTextEdit reports a bogus document height (it lays text out in a
        different container), so this uses QTextEdit.
        """
        doc = self.message.document()
        doc.setTextWidth(max(220, self.message.viewport().width()))
        height = int(doc.size().height()) + 16
        self.message.setFixedHeight(max(70, min(280, height)))

    def _find_app(self):
        widget = self.parentWidget()
        while widget is not None:
            app = getattr(widget, "app", None)
            if app is not None:
                return app
            widget = widget.parentWidget()
        return None

    def _action_label(self) -> str:
        if not self._actions:
            return "选择动作（可留空）"
        return f"选择动作（已选 {len(self._actions)} 个）"

    def _pick_actions(self) -> None:
        dlg = ActionPickerDialog(self._actions, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._actions = dlg.selected()
            self.action_btn.setText(self._action_label())

    def _clear_actions(self) -> None:
        self._actions = []
        self.action_btn.setText(self._action_label())

    def _set_color(self, value: str) -> None:
        self.color_hex.setText(value)
        self.color_btn.setIcon(_swatch(value))

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.color_hex.text() or "#2B6CF6"), self)
        if col.isValid():
            self._set_color(col.name())

    def _color_from_hex(self) -> None:
        text = self.color_hex.text().strip()
        if QColor(text).isValid():
            self.color_btn.setIcon(_swatch(text))
        else:
            self.color_hex.setText(self._phase.color)

    def _pick_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择铃声", "",
                                              "音频 (*.wav *.mp3 *.ogg *.flac)")
        if path:
            self.sound.addItem(Path(path).stem, path)
            self.sound.setCurrentIndex(self.sound.count() - 1)

    def _preview(self) -> None:
        app = self._find_app()
        audio = getattr(app, "audio", None) if app is not None else None
        if audio is None:
            self.sound_status.setText("无法试听：没有找到音频模块")
            return
        volume = int(getattr(app.cfg.settings, "volume", 60))
        target = self.sound.currentData() or str(audio_mod.SOUND_DIR / "bell_soft.wav")
        self.sound_status.setText("试听中…")
        audio.preview(target, max(20, volume))
        QTimer.singleShot(700, self._check_preview)

    def _check_preview(self) -> None:
        app = self._find_app()
        audio = getattr(app, "audio", None) if app is not None else None
        error = getattr(audio, "last_error", "") if audio is not None else ""
        self.sound_status.setText(f"播放失败：{error}" if error else "")

    # -- result
    def value(self) -> config.Phase:
        ph = self._phase
        ph.name = self.name.text().strip() or "阶段"
        ph.kind = self.kind.currentData()
        ph.minutes = float(self.minutes.value())
        ph.use_range = self.use_range.isChecked()
        ph.minutes_min = float(self.range_min.value())
        ph.minutes_max = float(self.range_max.value())
        ph.color = self.color_hex.text().strip() or "#2B6CF6"
        ph.icon = self.icon.text().strip()
        ph.sound = self.sound.currentData() or ""
        ph.message = self.message.toPlainText().strip()
        ph.require_leave = self.require_leave.isChecked()
        ph.allow_skip = self.allow_skip.isChecked()
        ph.pre_alert = self.pre_alert.isChecked()
        ph.pre_alert_min = int(self.pre_min.value())
        ph.pre_alert_max = int(self.pre_max.value())
        ph.actions = list(self._actions)
        ph.hooks_start = self.hooks_start.hooks()
        ph.hooks_end = self.hooks_end.hooks()
        return ph


# ---------------------------------------------------------- action picker ---
class ActionPickerDialog(QDialog):
    """Checkbox list over the built-in movement library, grouped by body area."""

    def __init__(self, selected: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择动作")
        self.setMinimumSize(520, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(8)

        hint = QLabel("这些动作会在休息提醒里显示，带简笔画和步骤。")
        hint.setObjectName("Faint")
        root.addWidget(hint)

        self.list = QListWidget()
        root.addWidget(self.list, 1)

        current_area = ""
        for action in actions_mod.ACTIONS:
            if action.area_label != current_area:
                current_area = action.area_label
                header = QListWidgetItem(f"— {current_area} —")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list.addItem(header)
            item = QListWidgetItem(QIcon(svg_pixmap(action.svg, 28)),
                                   f"{action.name}   ·   {action.seconds} 秒")
            item.setData(Qt.ItemDataRole.UserRole, action.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if action.id in selected
                               else Qt.CheckState.Unchecked)
            item.setToolTip(action.detail)
            self.list.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected(self) -> list[str]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            aid = item.data(Qt.ItemDataRole.UserRole)
            if aid and item.checkState() == Qt.CheckState.Checked:
                out.append(aid)
        return out

# QueueDialog now lives in queue_editor.py (it grew a third section);
# re-exported so `from .editors import QueueDialog` keeps working.
from .queue_editor import QueueDialog  # noqa: E402,F401
