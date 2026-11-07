"""Main pages: timer, queue, statistics, settings."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QTimeEdit, QVBoxLayout, QWidget)

from .. import config, stats
from .. import engine as engine_mod
from .. import hooks as hooks_mod
from .. import hotkey as hotkey_mod
from .. import theme as theme_mod
from .spinbox import NumberBox
from .widgets import Card, RingWidget, StatChip, WeekChart, format_seconds, qcolor


def _hbox_widget(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    return w


# ------------------------------------------------------------------ timer ---
class TimerPage(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(12)

        # elevation banner: invisible in the normal case, impossible to miss when
        # it matters — an elevated parent breaks browsers and packaged apps
        self.admin_bar = QFrame()
        self.admin_bar.setObjectName("CardFlat")
        bar = QHBoxLayout(self.admin_bar)
        bar.setContentsMargins(14, 8, 14, 8)
        bar.setSpacing(10)
        warn = QLabel("当前以管理员权限运行：浏览器会提示“已有实例以提升的权限运行”，"
                      "记事本这类商店应用也打不开。")
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {self.app.theme['palette']['warning']};")
        fix_admin = QPushButton("以普通权限重启")
        fix_admin.setObjectName("Ghost")
        fix_admin.clicked.connect(self.app.relaunch_unelevated)
        bar.addWidget(warn, 1)
        bar.addWidget(fix_admin)
        self.admin_bar.setVisible(hooks_mod.is_elevated())
        root.addWidget(self.admin_bar)

        head = QHBoxLayout()
        head.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = QLabel("未开始")
        self.title.setObjectName("H1")
        self.meta = QLabel("")
        self.meta.setObjectName("Muted")
        col.addWidget(self.title)
        col.addWidget(self.meta)
        head.addLayout(col)
        head.addStretch()

        self.queue_box = QComboBox()
        self.queue_box.setMinimumWidth(150)
        self.queue_box.currentIndexChanged.connect(self._on_queue_picked)
        head.addWidget(self.queue_box)

        self.theme_box = QComboBox()
        self.theme_box.setMinimumWidth(130)
        self.theme_box.currentIndexChanged.connect(self._on_theme_picked)
        head.addWidget(self.theme_box)
        root.addLayout(head)

        card = Card()
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(18, 14, 18, 14)
        self.ring = RingWidget(app.theme)
        self.ring.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_lay.addWidget(self.ring, 1, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(card, 1)

        self.next_bar = QFrame()
        self.next_bar.setObjectName("CardFlat")
        nb = QHBoxLayout(self.next_bar)
        nb.setContentsMargins(14, 9, 14, 9)
        nb.setSpacing(8)
        self.next_dot = QLabel("●")
        self.next_dot.setFixedWidth(12)
        self.next_label = QLabel("下一段 · —")
        self.next_label.setObjectName("Muted")
        nb.addWidget(self.next_dot)
        nb.addWidget(self.next_label)
        nb.addStretch()
        root.addWidget(self.next_bar)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.start_btn = QPushButton("开始")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumWidth(112)
        self.skip_btn = QPushButton("跳过本段")
        self.skip_btn.setObjectName("Ghost")
        self.snooze_btn = QPushButton("推迟 5 分钟")
        self.snooze_btn.setObjectName("Ghost")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("Ghost")
        for b in (self.start_btn, self.skip_btn, self.snooze_btn, self.stop_btn):
            btns.addWidget(b)
        btns.addStretch()
        root.addLayout(btns)

        chips = QHBoxLayout()
        chips.setSpacing(10)
        self.chip_focus = StatChip("今日专注")
        self.chip_breaks = StatChip("休息完成")
        self.chip_skips = StatChip("跳过")
        self.chip_sit = StatChip("连续坐姿")
        for c in (self.chip_focus, self.chip_breaks, self.chip_skips, self.chip_sit):
            chips.addWidget(c)
        root.addLayout(chips)

        self.start_btn.clicked.connect(self.app.toggle_timer)
        self.skip_btn.clicked.connect(self.app.skip_phase)
        self.snooze_btn.clicked.connect(self.app.snooze_phase)
        self.stop_btn.clicked.connect(self.app.stop_timer)

        self.reload()
        self.refresh()
        self.refresh_stats()

    def set_sitting(self, minutes: float) -> None:
        self.chip_sit.set_value(f"{minutes:.0f} min")

    # -- combos
    def reload(self) -> None:
        self.queue_box.blockSignals(True)
        self.queue_box.clear()
        for q in self.app.cfg.queues:
            self.queue_box.addItem(q.name, q.id)
        idx = self.queue_box.findData(self.app.engine.queue.id)
        if idx >= 0:
            self.queue_box.setCurrentIndex(idx)
        self.queue_box.blockSignals(False)

        self.theme_box.blockSignals(True)
        self.theme_box.clear()
        for t in theme_mod.list_themes():
            self.theme_box.addItem(t["name"], t["id"])
        cur = self.app.cfg.settings.theme
        i = self.theme_box.findData(cur)
        if i >= 0:
            self.theme_box.setCurrentIndex(i)
        self.theme_box.blockSignals(False)

    def _on_queue_picked(self, _index: int) -> None:
        qid = self.queue_box.currentData()
        if qid:
            self.app.switch_queue(qid)

    def _on_theme_picked(self, _index: int) -> None:
        tid = self.theme_box.currentData()
        if tid:
            self.app.switch_theme(tid)

    # -- state
    def _meta_text(self) -> str:
        eng = self.app.engine
        q = eng.queue
        text = f"{len(q.rounds)} 轮 · 共 {q.phase_count()} 段"
        if q.entry or q.exit:
            text += f"（含起止 {q.total_phases()} 段）"
        text += f" · {q.loop_label()}"
        if q.loop_mode == "until":
            remaining = eng.until_remaining()
            if remaining is not None and eng.state in (engine_mod.RUNNING,
                                                       engine_mod.PAUSED):
                if remaining > 1:
                    text += f" · 距 {q.until_time} 还有 {format_seconds(remaining)}"
                else:
                    text += f" · 已过 {q.until_time}，本轮结束就收工"
        return text

    def refresh(self) -> None:
        eng = self.app.engine
        q = eng.queue
        self.meta.setText(self._meta_text())
        self.title.setText(q.name)

        state = eng.state
        if state == engine_mod.RUNNING:
            self.start_btn.setText("暂停")
        elif state == engine_mod.PAUSED:
            self.start_btn.setText("继续")
        elif state == engine_mod.ALERT:
            self.start_btn.setText("结算中")
        else:
            self.start_btn.setText("开始")

        self.skip_btn.setEnabled(state in (engine_mod.RUNNING, engine_mod.PAUSED,
                                           engine_mod.ALERT))
        self.snooze_btn.setEnabled(state == engine_mod.ALERT and eng.can_snooze())
        self.snooze_btn.setText(f"推迟 {self.app.cfg.settings.snooze_minutes} 分钟")
        self.stop_btn.setEnabled(state != engine_mod.IDLE)
        self.ring.set_content(paused=state == engine_mod.PAUSED)

        if state == engine_mod.IDLE and eng.phase is None:
            self.ring.set_phase_color(self.app.theme["palette"]["accent"])
            if eng.was_stopped():
                self.ring.set_content(time_text="00:00", name="已停止",
                                      sub="本次队列已结束 · 点开始重新计时", icon="")
            else:
                self.ring.set_content(time_text="00:00", name="准备开始",
                                      sub=f"共 {q.phase_count()} 段 · 点开始进入第一段", icon="")

        nxt = eng.next_phase()
        if nxt is not None:
            self.next_dot.setStyleSheet(f"color: {nxt.color};")
            self.next_label.setText(
                f"下一段 · {nxt.name} · {format_seconds(nxt.resolve_seconds())}")
        else:
            self.next_dot.setStyleSheet(f"color: {self.app.theme['palette']['text_faint']};")
            self.next_label.setText("下一段 · 队列结束")

    def on_phase(self, phase, info: dict) -> None:
        stage = info.get("stage", "loop")
        if stage == "loop":
            sub = f"第 {info['index']} 段 / 共 {info['count']} 段 · 第 {info['loop']} 轮"
        else:
            sub = f"{info.get('stage_label', '阶段')} · 第 {info['index']} 段 / 共 {info['count']} 段"
        self.ring.set_phase_color(phase.color)
        self.ring.set_content(
            name=phase.name,
            icon=phase.icon or "",
            sub=sub,
            time_text=format_seconds(self.app.engine.remaining()),
            progress=self.app.engine.progress(),
        )
        self.refresh()

    def on_tick(self, remaining: float, total: float) -> None:
        self.ring.set_content(time_text=format_seconds(remaining),
                              progress=self.app.engine.progress())
        if self.app.engine.queue.loop_mode == "until":
            self.meta.setText(self._meta_text())

    def refresh_stats(self) -> None:
        s = stats.today_summary()
        self.chip_focus.set_value(f"{s['focus_minutes']:.0f} min")
        self.chip_breaks.set_value(str(s["breaks"]))
        self.chip_skips.set_value(str(s["skips"]))
        if hasattr(self.app, "sitting"):
            self.chip_sit.set_value(f"{self.app.sitting.minutes():.0f} min")


# ------------------------------------------------------------------ queue ---
class QueuePage(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("队列")
        title.setObjectName("H1")
        head.addWidget(title)

        # the queue itself is the selector: pick one here to view / edit / delete
        self.queue_box = QComboBox()
        self.queue_box.setMinimumWidth(250)
        self.queue_box.setToolTip("切换要查看的队列；编辑与删除只作用于当前这个")
        self.queue_box.currentIndexChanged.connect(self._on_queue_picked)
        head.addWidget(self.queue_box)

        head.addStretch()
        self.new_btn = QPushButton("新建")
        self.new_btn.setObjectName("Ghost")
        self.new_btn.clicked.connect(self._new_queue)
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setObjectName("Ghost")
        self.edit_btn.clicked.connect(self._edit_queue)
        self.del_btn = QPushButton("删除")
        self.del_btn.setObjectName("Ghost")
        self.del_btn.clicked.connect(self._delete_queue)
        for b in (self.new_btn, self.edit_btn, self.del_btn):
            head.addWidget(b)
        root.addLayout(head)

        self.sub = QLabel("")
        self.sub.setObjectName("Muted")
        self.sub.setWordWrap(True)
        root.addWidget(self.sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 8, 0)
        self.body_lay.setSpacing(10)
        scroll.setWidget(self.body)
        root.addWidget(scroll, 1)
        self.rebuild()

    # -- queue selector
    def reload_queues(self) -> None:
        box = self.queue_box
        box.blockSignals(True)
        box.clear()
        for q in self.app.cfg.queues:
            box.addItem(f"{q.name}  ·  {q.phase_count()} 段/轮 · {q.loop_label()}", q.id)
            box.setItemData(box.count() - 1, q.description or "（没有说明）",
                            Qt.ItemDataRole.ToolTipRole)
        index = box.findData(self.app.engine.queue.id)
        if index >= 0:
            box.setCurrentIndex(index)
        box.blockSignals(False)

    def _on_queue_picked(self, index: int) -> None:
        qid = self.queue_box.itemData(index)
        if qid and qid != self.app.engine.queue.id:
            self.app.switch_queue(qid)

    def rebuild(self) -> None:
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)          # hide/defer immediately, not only at deleteLater
                w.deleteLater()

        self.reload_queues()
        q = self.app.engine.queue
        note = q.description or "（没有说明）"
        self.sub.setText(f"{note}   ·   {q.loop_label()}   ·   共 {len(self.app.cfg.queues)} 个队列")
        self.del_btn.setEnabled(len(self.app.cfg.queues) > 1)

        if q.entry:
            self.body_lay.addWidget(self._phase_card("起始阶段", q.entry))
        for rnd in q.rounds:
            self.body_lay.addWidget(self._phase_card(rnd.name, rnd.phases))
        if q.exit:
            self.body_lay.addWidget(self._phase_card("结束阶段", q.exit))
        self.body_lay.addStretch()

    def _phase_card(self, title: str, phases) -> "Card":
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("H2")
        lay.addWidget(head)
        for ph in phases:
            row = QHBoxLayout()
            row.setSpacing(10)
            bar = QLabel()
            bar.setFixedSize(4, 26)
            bar.setStyleSheet(f"background: {ph.color}; border-radius: 2px;")
            row.addWidget(bar)
            icon = QLabel(ph.icon or "·")
            icon.setFixedWidth(22)
            row.addWidget(icon)
            name = QLabel(ph.name)
            row.addWidget(name)
            if ph.use_range:
                dur = f"{ph.minutes_min:g}–{ph.minutes_max:g} 分钟"
            else:
                dur = f"{ph.minutes:g} 分钟"
            d = QLabel(dur)
            d.setObjectName("Muted")
            row.addWidget(d)
            tags = []
            if ph.require_leave:
                tags.append("需离座")
            if not ph.allow_skip:
                tags.append("不可跳过")
            if ph.pre_alert:
                tags.append(f"提前 {ph.pre_alert_min}-{ph.pre_alert_max}s 预告")
            if ph.hooks_start or ph.hooks_end:
                tags.append("有钩子")
            if tags:
                t = QLabel(" · ".join(tags))
                t.setObjectName("Faint")
                row.addWidget(t)
            row.addStretch()
            lay.addLayout(row)
        return card

    # -- editing
    def _edit_queue(self) -> None:
        from .editors import QueueDialog

        queue = self.app.engine.queue
        dlg = QueueDialog(queue, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.app.replace_queue(dlg.value())

    def _new_queue(self) -> None:
        from .editors import QueueDialog

        draft = config.Queue(
            name="新队列", loop_count=1,
            rounds=[config.Round(name="第 1 轮", phases=[
                config.Phase(name="专注工作", kind="focus", minutes=25,
                             color="#2B6CF6", icon="🧑‍💻"),
                config.Phase(name="休息", kind="break", minutes=5,
                             color="#12B886", icon="☕"),
            ])],
        )
        dlg = QueueDialog(draft, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        queue = dlg.value()
        self.app.cfg.queues.append(queue)
        self.app.switch_queue(queue.id)
        self.app.win.timer_page.reload()

    def _delete_queue(self) -> None:
        queue = self.app.engine.queue
        if len(self.app.cfg.queues) <= 1:
            QMessageBox.information(self, "无法删除", "至少要保留一个队列。")
            return
        ok = QMessageBox.question(self, "删除队列", f"确定删除「{queue.name}」？此操作不可撤销。")
        if ok != QMessageBox.StandardButton.Yes:
            return
        self.app.cfg.queues = [q for q in self.app.cfg.queues if q.id != queue.id]
        self.app.switch_queue(self.app.cfg.queues[0].id)
        self.app.win.timer_page.reload()


# ------------------------------------------------------------------ stats ---
class StatsPage(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel("统计")
        title.setObjectName("H1")
        sub = QLabel("本地记录，不联网")
        sub.setObjectName("Muted")
        col.addWidget(title)
        col.addWidget(sub)
        head.addLayout(col)
        head.addStretch()
        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.setObjectName("Ghost")
        self.export_btn.clicked.connect(self._export)
        head.addWidget(self.export_btn)
        root.addLayout(head)

        chips = QHBoxLayout()
        chips.setSpacing(10)
        self.chip_focus = StatChip("今日专注")
        self.chip_breaks = StatChip("休息完成")
        self.chip_skips = StatChip("跳过")
        self.chip_sit = StatChip("最长连续坐姿")
        for c in (self.chip_focus, self.chip_breaks, self.chip_skips, self.chip_sit):
            chips.addWidget(c)
        root.addLayout(chips)

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 10)
        head2 = QLabel("最近 7 天专注时长")
        head2.setObjectName("H2")
        lay.addWidget(head2)
        self.chart = WeekChart(app.theme)
        lay.addWidget(self.chart, 1)
        root.addWidget(card, 1)
        self.refresh()

    def refresh(self) -> None:
        s = stats.today_summary()
        self.chip_focus.set_value(f"{s['focus_minutes']:.0f} min")
        self.chip_breaks.set_value(str(s["breaks"]))
        self.chip_skips.set_value(str(s["skips"]))
        self.chip_sit.set_value(f"{s['longest_sit']:.0f} min" if s["longest_sit"] else "—")
        self.chart.set_data(stats.week_series(7))

    def _export(self) -> None:
        default = f"circlock-{datetime.now():%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出统计", str(config.data_dir() / default),
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            n = stats.export_csv(path)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"已导出 {n} 条记录到\n{path}")


# --------------------------------------------------------------- settings ---
class SettingsPage(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(12)

        title = QLabel("设置")
        title.setObjectName("H1")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(10)

        self._theme_row(lay)
        self._alert_rows(lay)
        self._schedule_rows(lay)
        self._meeting_rows(lay)
        self._life_rows(lay)
        self._health_rows(lay)
        self._window_rows(lay)
        self._about_rows(lay)

        lay.addStretch()
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

    # -- helpers
    def _group(self, lay: QVBoxLayout, title: str) -> QGridLayout:
        card = Card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("H2")
        outer.addWidget(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        lay.addWidget(card)
        return grid

    def _row(self, grid: QGridLayout, rowi: int, text: str, widget: QWidget,
             hint: str = "") -> None:
        label = QLabel(text)
        grid.addWidget(label, rowi, 0)
        grid.addWidget(widget, rowi, 1)
        if hint:
            h = QLabel(hint)
            h.setObjectName("Faint")
            grid.addWidget(h, rowi, 2)

    def _check(self, text: str, value: bool, on_change) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(value)
        box.toggled.connect(on_change)
        return box

    # -- sections
    def _theme_row(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "外观")
        s = self.app.cfg.settings
        self.theme_combo = QComboBox()
        for t in theme_mod.list_themes():
            self.theme_combo.addItem(t["name"], t["id"])
        i = self.theme_combo.findData(s.theme)
        if i >= 0:
            self.theme_combo.setCurrentIndex(i)
        self.theme_combo.currentIndexChanged.connect(
            lambda: self.app.switch_theme(self.theme_combo.currentData()))
        self._row(grid, 0, "主题", self.theme_combo, "themes/*.json 可自己加")

        self.accent_btn = QPushButton("选择强调色")
        self.accent_btn.setObjectName("Ghost")
        self.accent_btn.clicked.connect(self._pick_accent)
        reset = QPushButton("恢复主题默认")
        reset.setObjectName("Link")
        reset.clicked.connect(self._reset_accent)
        accent_row = QWidget()
        ar = QHBoxLayout(accent_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(6)
        ar.addWidget(self.accent_btn)
        ar.addWidget(reset)
        ar.addStretch()
        self._row(grid, 1, "强调色", accent_row, "留空则跟随主题")

    def _alert_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "提醒")
        s = self.app.cfg.settings

        self._row(grid, 0, "声音", QLabel(""), "")
        grid.addWidget(self._check("启用铃声", s.sound_enabled,
                                   lambda v: self._set("sound_enabled", v)), 0, 1)

        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(s.volume)
        self.vol.valueChanged.connect(lambda v: self._set("volume", v))
        self._row(grid, 1, "音量", self.vol, f"{s.volume}%")

        grid.addWidget(self._check("渐进式提醒（先气泡，超时升级）", s.progressive,
                                   lambda v: self._set("progressive", v)), 2, 1)
        grid.addWidget(self._check("直接全屏提醒", s.fullscreen,
                                   lambda v: self._set("fullscreen", v)), 3, 1)
        grid.addWidget(self._check("窗口置顶", s.topmost,
                                   lambda v: self._set("topmost", v)), 4, 1)
        grid.addWidget(self._check("抢焦点（强制切到提醒窗口）", s.steal_focus,
                                   lambda v: self._set("steal_focus", v)), 5, 1)

        self.toast_spin = NumberBox()
        self.toast_spin.setRange(5, 120)
        self.toast_spin.setValue(s.toast_seconds)
        self.toast_spin.setSuffix(" 秒")
        self.toast_spin.valueChanged.connect(lambda v: self._set("toast_seconds", v))
        self._row(grid, 6, "升级到全屏前等待", self.toast_spin)

        self.snooze_spin = NumberBox()
        self.snooze_spin.setRange(1, 30)
        self.snooze_spin.setValue(s.snooze_minutes)
        self.snooze_spin.setSuffix(" 分钟")
        self.snooze_spin.valueChanged.connect(lambda v: self._set("snooze_minutes", v))
        self._row(grid, 7, "推迟时长", self.snooze_spin)

        self.limit_spin = NumberBox()
        self.limit_spin.setRange(0, 10)
        self.limit_spin.setValue(s.snooze_limit)
        self.limit_spin.setSuffix(" 次")
        self.limit_spin.valueChanged.connect(lambda v: self._set("snooze_limit", v))
        self._row(grid, 8, "推迟次数上限", self.limit_spin, "0 = 不允许推迟")

    def _schedule_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "时段计划")
        s = self.app.cfg.settings
        self.sched_enable = self._check("按工作时段自动开始 / 结束队列", s.schedule_enabled,
                                        lambda v: self._set("schedule_enabled", v))
        grid.addWidget(self.sched_enable, 0, 1)

        days_row = QHBoxLayout()
        days_row.setSpacing(6)
        self.day_boxes: list[QCheckBox] = []
        for i, label in enumerate(("一", "二", "三", "四", "五", "六", "日"), start=1):
            cb = QCheckBox(label)
            cb.setChecked(i in (s.schedule_days or []))
            cb.toggled.connect(self._sync_days)
            days_row.addWidget(cb)
            self.day_boxes.append(cb)
        days_row.addStretch()
        self._row(grid, 1, "生效日", _hbox_widget(days_row))

        self.win_edits: list[tuple[QTimeEdit, QTimeEdit]] = []
        defaults = [["09:00", "12:00"], ["13:30", "18:30"]]
        for idx, label in enumerate(("上午", "下午")):
            window = s.schedule_windows[idx] if idx < len(s.schedule_windows) else defaults[idx]
            row = QHBoxLayout()
            row.setSpacing(6)
            start = QTimeEdit()
            end = QTimeEdit()
            for box, value in ((start, window[0]), (end, window[1])):
                box.setDisplayFormat("HH:mm")
                box.setTime(QTime.fromString(value, "HH:mm"))
            start.timeChanged.connect(self._sync_windows)
            end.timeChanged.connect(self._sync_windows)
            row.addWidget(start)
            row.addWidget(QLabel("—"))
            row.addWidget(end)
            row.addStretch()
            self.win_edits.append((start, end))
            self._row(grid, 2 + idx, label, _hbox_widget(row))

    def _sync_days(self) -> None:
        self._set("schedule_days",
                  [i for i, cb in enumerate(self.day_boxes, start=1) if cb.isChecked()])

    def _sync_windows(self) -> None:
        self._set("schedule_windows",
                  [[a.time().toString("HH:mm"), b.time().toString("HH:mm")]
                   for a, b in self.win_edits])

    def _meeting_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "会议模式与勿扰")
        s = self.app.cfg.settings

        row = QHBoxLayout()
        row.setSpacing(6)
        self.hotkey_edit = QLineEdit(s.meeting_hotkey)
        self.hotkey_edit.setFixedWidth(150)
        apply_btn = QPushButton("应用")
        apply_btn.setObjectName("Ghost")
        apply_btn.clicked.connect(self._apply_hotkey)
        self.hotkey_status = QLabel("")
        self.hotkey_status.setObjectName("Faint")
        row.addWidget(self.hotkey_edit)
        row.addWidget(apply_btn)
        row.addWidget(self.hotkey_status)
        row.addStretch()
        self._row(grid, 0, "会议模式热键", _hbox_widget(row), "如 Ctrl+Alt+M")

        self.dnd_check = self._check("启用勿扰时段（静音、不弹窗）", s.dnd_enabled,
                                     lambda v: self._set("dnd_enabled", v))
        grid.addWidget(self.dnd_check, 1, 1)

        dnd = s.dnd_ranges[0] if s.dnd_ranges else ["12:00", "13:30"]
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.dnd_start = QTimeEdit()
        self.dnd_end = QTimeEdit()
        for box, value in ((self.dnd_start, dnd[0]), (self.dnd_end, dnd[1])):
            box.setDisplayFormat("HH:mm")
            box.setTime(QTime.fromString(value, "HH:mm"))
        self.dnd_start.timeChanged.connect(self._sync_dnd)
        self.dnd_end.timeChanged.connect(self._sync_dnd)
        row2.addWidget(self.dnd_start)
        row2.addWidget(QLabel("—"))
        row2.addWidget(self.dnd_end)
        row2.addStretch()
        self._row(grid, 2, "勿扰时段", _hbox_widget(row2), "跨午夜也支持")

        hint = QLabel("会议模式：冻结队列、停止铃声、不弹窗；再按一次热键恢复，时间顺延。")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        grid.addWidget(hint, 3, 1, 1, 2)

    def _sync_dnd(self) -> None:
        self._set("dnd_ranges", [[self.dnd_start.time().toString("HH:mm"),
                                  self.dnd_end.time().toString("HH:mm")]])

    def _apply_hotkey(self) -> None:
        text = self.hotkey_edit.text().strip()
        if hotkey_mod.parse_hotkey(text) is None:
            self.hotkey_status.setText("格式无法解析")
            return
        self._set("meeting_hotkey", text)
        ok = self.app._register_hotkey()
        self.hotkey_status.setText("已注册" if ok else f"失败：{self.app.hotkey.error}")

    def _life_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "启动与常驻")
        s = self.app.cfg.settings
        grid.addWidget(self._check("开机自启动", s.autostart,
                                   lambda v: self._set("autostart", v)), 0, 1)
        grid.addWidget(self._check("启动后自动开始默认队列", s.autostart_queue,
                                   lambda v: self._set("autostart_queue", v)), 1, 1)
        grid.addWidget(self._check("关闭窗口时最小化到托盘", s.close_to_tray,
                                   lambda v: self._set("close_to_tray", v)), 2, 1)
        grid.addWidget(self._check("显示角落迷你悬浮窗", s.show_hud,
                                   lambda v: self._set("show_hud", v)), 3, 1)

    def _health_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "久坐与健康")
        s = self.app.cfg.settings
        self.sit_spin = NumberBox()
        self.sit_spin.setRange(20, 120)
        self.sit_spin.setValue(s.sitting_limit_minutes)
        self.sit_spin.setSuffix(" 分钟")
        self.sit_spin.valueChanged.connect(lambda v: self._set("sitting_limit_minutes", v))
        self._row(grid, 0, "连续坐姿上限", self.sit_spin, "超过就强制提醒")

        grid.addWidget(self._check("休息阶段需要确认已离座", s.break_confirm,
                                   lambda v: self._set("break_confirm", v)), 1, 1)

        self.idle_spin = NumberBox()
        self.idle_spin.setRange(30, 1800)
        self.idle_spin.setValue(s.idle_seconds)
        self.idle_spin.setSuffix(" 秒")
        self.idle_spin.valueChanged.connect(lambda v: self._set("idle_seconds", v))
        self._row(grid, 2, "无操作判定阈值", self.idle_spin)
        grid.addWidget(self._check("离开时自动暂停队列", s.auto_pause_on_idle,
                                   lambda v: self._set("auto_pause_on_idle", v)), 3, 1)

        water_row = QHBoxLayout()
        water_row.setSpacing(8)
        water_row.addWidget(self._check("饮水提醒", s.water_enabled,
                                        lambda v: self._set("water_enabled", v)))
        self.water_spin = NumberBox()
        self.water_spin.setRange(15, 240)
        self.water_spin.setValue(s.water_interval_minutes)
        self.water_spin.setSuffix(" 分钟")
        self.water_spin.valueChanged.connect(lambda v: self._set("water_interval_minutes", v))
        water_row.addWidget(self.water_spin)
        water_row.addStretch()
        self._row(grid, 4, "补水", _hbox_widget(water_row))

        grid.addWidget(self._check("护眼 20-20-20（每 20 分钟）", s.eye_enabled,
                                   lambda v: self._set("eye_enabled", v)), 5, 1)

    def _window_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "数据")
        row = QHBoxLayout()
        open_btn = QPushButton("打开数据目录")
        open_btn.setObjectName("Ghost")
        open_btn.clicked.connect(self._open_data)
        row.addWidget(open_btn)
        row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        self._row(grid, 0, "配置与历史", holder, str(config.data_dir()))

    def _about_rows(self, lay: QVBoxLayout) -> None:
        grid = self._group(lay, "关于与退出")
        from .. import __version__, hooks

        info = QLabel(f"{config.DISPLAY_NAME} {__version__}   ·   数据目录：{config.data_dir()}")
        info.setObjectName("Faint")
        info.setWordWrap(True)
        grid.addWidget(info, 0, 0, 1, 2)

        row = QHBoxLayout()
        row.setSpacing(8)
        log_btn = QPushButton("查看钩子日志")
        log_btn.setObjectName("Ghost")
        log_btn.setToolTip("外部动作的执行记录，失败原因都写在这里")
        log_btn.clicked.connect(self._open_hook_log)
        diag_btn = QPushButton("环境诊断")
        diag_btn.setObjectName("Ghost")
        diag_btn.setToolTip("看看链接/文件会用哪个程序打开、当前是不是管理员模式")
        diag_btn.clicked.connect(self._show_diagnostics)
        quit_btn = QPushButton("关闭 CirClock")
        quit_btn.setObjectName("Danger")
        quit_btn.setToolTip("结束进程，后台计时也会停止")
        quit_btn.clicked.connect(self.app.quit)
        row.addWidget(log_btn)
        row.addWidget(diag_btn)
        row.addStretch()
        row.addWidget(quit_btn)
        self._row(grid, 1, "退出", _hbox_widget(row))

        if hooks.is_elevated():
            warn = QLabel("当前以管理员身份运行：浏览器/文件可能打不开或报“提升权限”错误。")
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {self.app.theme['palette']['warning']};")
            grid.addWidget(warn, 2, 0, 1, 2)
            fix_btn = QPushButton("以普通权限重启")
            fix_btn.setObjectName("Ghost")
            fix_btn.clicked.connect(self.app.relaunch_unelevated)
            grid.addWidget(fix_btn, 3, 1)

    def _open_hook_log(self) -> None:
        from .. import hooks

        path = hooks.log_path()
        if not path.exists():
            QMessageBox.information(self, "钩子日志", "还没有执行过外部动作。")
            return
        hooks.run_one(config.Hook(type="open", target=str(path)))

    def _hook_targets(self) -> list[str]:
        found: list[str] = []
        for q in self.app.cfg.queues:
            groups = [q.entry, q.exit] + [r.phases for r in q.rounds]
            for phases in groups:
                for phase in phases:
                    for hook in (phase.hooks_start + phase.hooks_end):
                        if hook.target and hook.target not in found:
                            found.append(hook.target)
        return found

    def _show_diagnostics(self) -> None:
        from .. import hooks

        targets = self._hook_targets()[:10]
        text = hooks.diagnose(targets)
        dlg = QDialog(self)
        dlg.setWindowTitle("环境诊断")
        dlg.resize(760, 540)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 12, 14, 12)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        lay.addWidget(box, 1)
        row = QHBoxLayout()
        copy = QPushButton("复制")
        copy.setObjectName("Ghost")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        close = QPushButton("关闭")
        close.setObjectName("Primary")
        close.clicked.connect(dlg.accept)
        row.addStretch()
        row.addWidget(copy)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    # -- actions
    def _set(self, key: str, value) -> None:
        setattr(self.app.cfg.settings, key, value)
        self.app.save()
        if key in ("water_enabled", "water_interval_minutes", "eye_enabled"):
            self.app.reminders.configure()

    def _pick_accent(self) -> None:
        col = QColorDialog.getColor(QColor(self.app.theme["palette"]["accent"]), self)
        if col.isValid():
            self.app.cfg.settings.accent = col.name()
            self.app.save()
            self.app.apply_theme()

    def _reset_accent(self) -> None:
        self.app.cfg.settings.accent = ""
        self.app.save()
        self.app.apply_theme()

    def _open_data(self) -> None:
        from .. import hooks
        hooks.run_one(config.Hook(type="open", target=str(config.data_dir())))
