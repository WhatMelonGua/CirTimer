"""Queue editor: identity, loop mode (count / forever / until a clock time),
and three ordered phase groups (起始阶段 -> 各轮 -> 结束阶段)."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QTimeEdit, QVBoxLayout, QWidget)

from .. import config
from .spinbox import NumberBox

LOOP_MODES = [
    ("count", "固定轮数"),
    ("forever", "无限循环"),
    ("until", "循环到某个时刻"),
]


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


class QueueDialog(QDialog):
    """Left: sections (起始 / 各轮 / 结束). Right: the phases of the selected one."""

    def __init__(self, queue: config.Queue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑队列")
        self.setMinimumSize(860, 640)
        self._queue = copy.deepcopy(queue)
        self._sections: list[dict] = []
        self._section_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        # ---- identity
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("名称"))
        self.name = QLineEdit(self._queue.name)
        self.name.setFixedWidth(180)
        head.addWidget(self.name)
        head.addSpacing(10)
        head.addWidget(QLabel("说明"))
        self.desc = QLineEdit(self._queue.description)
        head.addWidget(self.desc, 1)
        root.addLayout(head)

        # ---- loop mode
        loop = QHBoxLayout()
        loop.setSpacing(8)
        loop.addWidget(QLabel("循环"))
        self.loop_mode = QComboBox()
        for key, label in LOOP_MODES:
            self.loop_mode.addItem(label, key)
        self.loop_mode.setCurrentIndex(
            max(0, self.loop_mode.findData(self._queue.loop_mode)))
        loop.addWidget(self.loop_mode)

        self.count = NumberBox()
        self.count.setRange(1, 99)
        self.count.setValue(max(1, self._queue.loop_count or 1))
        self.count.setSuffix(" 轮")
        self.count.setFixedWidth(110)
        loop.addWidget(self.count)

        self.until = QTimeEdit()
        self.until.setDisplayFormat("HH:mm")
        self.until.setTime(QTime.fromString(self._queue.until_time or "18:30", "HH:mm"))
        self.until.setFixedWidth(90)
        loop.addWidget(self.until)

        self.loop_hint = QLabel("")
        self.loop_hint.setObjectName("Faint")
        loop.addWidget(self.loop_hint, 1)
        root.addLayout(loop)

        # ---- split
        split = QHBoxLayout()
        split.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        t = QLabel("轮次与阶段组")
        t.setObjectName("H2")
        left.addWidget(t)
        self.section_list = QListWidget()
        self.section_list.currentRowChanged.connect(self._on_section_changed)
        left.addWidget(self.section_list, 1)

        grid = QGridLayout()
        grid.setSpacing(6)
        for col, (text, slot) in enumerate((("添加轮", self._add_round),
                                            ("起始阶段", self._toggle_entry),
                                            ("结束阶段", self._toggle_exit))):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.clicked.connect(slot)
            grid.addWidget(b, 0, col)
        rename = QPushButton("重命名")
        rename.setObjectName("Ghost")
        rename.clicked.connect(self._rename_section)
        remove = QPushButton("删除")
        remove.setObjectName("Ghost")
        remove.clicked.connect(self._remove_section)
        grid.addWidget(rename, 1, 0)
        grid.addWidget(remove, 1, 1)
        left.addLayout(grid)
        split.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(6)
        t = QLabel("阶段（按顺序执行）")
        t.setObjectName("H2")
        right.addWidget(t)
        self.phase_list = QListWidget()
        self.phase_list.itemDoubleClicked.connect(lambda _: self._edit_phase())
        right.addWidget(self.phase_list, 1)
        pbtns = QHBoxLayout()
        pbtns.setSpacing(6)
        for text, slot in (("添加", self._add_phase), ("编辑", self._edit_phase),
                           ("删除", self._remove_phase), ("上移", lambda: self._move(-1)),
                           ("下移", lambda: self._move(1))):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.clicked.connect(slot)
            pbtns.addWidget(b)
        pbtns.addStretch()
        right.addLayout(pbtns)
        split.addLayout(right, 5)
        root.addLayout(split, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.loop_mode.currentIndexChanged.connect(self._sync_loop)
        self._sync_loop()
        self._reload_sections()

    # --------------------------------------------------------------- loop ---
    def _sync_loop(self) -> None:
        mode = self.loop_mode.currentData()
        self.count.setEnabled(mode == "count")
        self.until.setEnabled(mode == "until")
        self.loop_hint.setText({
            "count": "跑完设定的轮数就结束",
            "forever": "一直循环，直到你手动停止",
            "until": "每跑完一轮检查一次：已过该时刻就收尾，否则继续下一轮",
        }.get(mode, ""))

    # ----------------------------------------------------------- sections ---
    def _rebuild_sections(self) -> None:
        self._sections = []
        if self._queue.entry:
            self._sections.append({"kind": "entry", "label": "起始阶段",
                                   "phases": self._queue.entry, "round": None})
        for i, rnd in enumerate(self._queue.rounds):
            self._sections.append({"kind": "round", "label": rnd.name,
                                   "phases": rnd.phases, "round": i})
        if self._queue.exit:
            self._sections.append({"kind": "exit", "label": "结束阶段",
                                   "phases": self._queue.exit, "round": None})

    def _reload_sections(self) -> None:
        self._rebuild_sections()
        self.section_list.blockSignals(True)
        self.section_list.clear()
        for section in self._sections:
            item = QListWidgetItem(f"{section['label']}  ·  {len(section['phases'])} 段")
            if section["kind"] != "round":
                item.setForeground(QColor("#7C6CF6"))
            self.section_list.addItem(item)
        self.section_list.blockSignals(False)
        if self._sections:
            self._section_index = min(self._section_index, len(self._sections) - 1)
            self.section_list.setCurrentRow(self._section_index)
        else:
            self._section_index = -1
        self._reload_phases()

    def _current(self) -> dict | None:
        if 0 <= self._section_index < len(self._sections):
            return self._sections[self._section_index]
        return None

    def _on_section_changed(self, row: int) -> None:
        if row >= 0:
            self._section_index = row
            self._reload_phases()

    def _reload_phases(self) -> None:
        self.phase_list.clear()
        section = self._current()
        if section is None:
            return
        for ph in section["phases"]:
            dur = (f"{ph.minutes_min:g}–{ph.minutes_max:g} 分" if ph.use_range
                   else f"{ph.minutes:g} 分")
            tags = []
            if ph.require_leave:
                tags.append("离座")
            if not ph.allow_skip:
                tags.append("不可跳过")
            if ph.hooks_start or ph.hooks_end:
                tags.append("钩子")
            suffix = ("  ·  " + " / ".join(tags)) if tags else ""
            self.phase_list.addItem(
                QListWidgetItem(_swatch(ph.color), f"{ph.name}   {dur}{suffix}"))

    def _reload_counts(self) -> None:
        for i, section in enumerate(self._sections):
            item = self.section_list.item(i)
            if item is not None:
                item.setText(f"{section['label']}  ·  {len(section['phases'])} 段")

    # ------------------------------------------------------- section ops ---
    def _add_round(self) -> None:
        self._queue.rounds.append(config.Round(
            name=f"第 {len(self._queue.rounds) + 1} 轮",
            phases=[config.Phase(name="专注工作", kind="focus", minutes=25,
                                 color="#2B6CF6", icon="🧑‍💻"),
                    config.Phase(name="休息", kind="break", minutes=5,
                                 color="#12B886", icon="☕")]))
        self._section_index = len(self._queue.entry and [1] or []) + len(self._queue.rounds) - 1
        self._reload_sections()

    def _toggle_entry(self) -> None:
        if self._queue.entry:
            self._queue.entry.clear()
        else:
            self._queue.entry.append(config.Phase(
                name="开工准备", kind="custom", minutes=3, color="#7C6CF6", icon="🌅",
                message="整理桌面，列一下今天的重点。"))
        self._reload_sections()

    def _toggle_exit(self) -> None:
        if self._queue.exit:
            self._queue.exit.clear()
        else:
            self._queue.exit.append(config.Phase(
                name="收工", kind="custom", minutes=5, color="#7C6CF6", icon="🌙",
                message="保存工作，记录今天做完的事。"))
        self._reload_sections()

    def _rename_section(self) -> None:
        section = self._current()
        if section is None or section["kind"] != "round":
            return
        rnd = self._queue.rounds[section["round"]]
        text, ok = QInputDialog.getText(self, "重命名轮次", "名称", text=rnd.name)
        if ok and text.strip():
            rnd.name = text.strip()
            self._reload_sections()

    def _remove_section(self) -> None:
        section = self._current()
        if section is None:
            return
        if section["kind"] == "entry":
            self._queue.entry.clear()
        elif section["kind"] == "exit":
            self._queue.exit.clear()
        elif len(self._queue.rounds) > 1:
            del self._queue.rounds[section["round"]]
        else:
            return
        self._section_index = max(0, self._section_index - 1)
        self._reload_sections()

    # --------------------------------------------------------- phase ops ---
    def _phases(self) -> list[config.Phase]:
        section = self._current()
        return section["phases"] if section else []

    def _phase_dialog(self, phase: config.Phase) -> "QDialog":
        from .editors import PhaseDialog

        return PhaseDialog(phase, self)

    def _add_phase(self) -> None:
        section = self._current()
        if section is None:
            return
        dlg = self._phase_dialog(config.Phase(name="新阶段", minutes=25, icon="⏱"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            section["phases"].append(dlg.value())
            self._reload_phases()
            self._reload_counts()

    def _edit_phase(self) -> None:
        phases = self._phases()
        row = self.phase_list.currentRow()
        if not (0 <= row < len(phases)):
            return
        dlg = self._phase_dialog(phases[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            phases[row] = dlg.value()
            self._reload_phases()
            self._reload_counts()

    def _remove_phase(self) -> None:
        section = self._current()
        row = self.phase_list.currentRow()
        if section is None:
            return
        phases = section["phases"]
        if not (0 <= row < len(phases)):
            return
        if len(phases) <= 1 and section["kind"] != "round":
            return                      # keep at least one phase in entry / exit
        if len(phases) <= 1:
            return
        del phases[row]
        self._reload_phases()
        self._reload_counts()

    def _move(self, delta: int) -> None:
        phases = self._phases()
        row = self.phase_list.currentRow()
        target = row + delta
        if 0 <= row < len(phases) and 0 <= target < len(phases):
            phases[row], phases[target] = phases[target], phases[row]
            self._reload_phases()
            self.phase_list.setCurrentRow(target)

    # ------------------------------------------------------------ result ---
    def value(self) -> config.Queue:
        q = self._queue
        q.name = self.name.text().strip() or "队列"
        q.description = self.desc.text().strip()
        q.loop_mode = self.loop_mode.currentData() or "count"
        q.loop_count = int(self.count.value())
        q.until_time = self.until.time().toString("HH:mm")
        return q
