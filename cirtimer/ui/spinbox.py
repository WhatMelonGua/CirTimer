"""Spin boxes with hand-drawn +/- steppers.

Qt's own up/down buttons lose their arrows as soon as a stylesheet touches a
QSpinBox (QStyleSheetStyle draws the frame but no glyph), which leaves the two
little blank boxes the user complained about. We shrink the native buttons to
zero width via the stylesheet — note that ``setButtonSymbols(NoButtons)`` is NOT
an option, it collapses the edit field to 1px — and overlay two focus-less
QToolButtons showing a real "+" and "−".
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QSpinBox, QToolButton

STEP_WIDTH = 20


class _Steppers:
    """Mixin: adds the two overlay buttons and keeps them pinned to the right."""

    def _install_steppers(self) -> None:
        self.setObjectName("Spin")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._up_btn = QToolButton(self)
        self._down_btn = QToolButton(self)
        for button, text, tip in ((self._up_btn, "+", "增加"),
                                  (self._down_btn, "−", "减少")):
            button.setObjectName("SpinStep")
            button.setText(text)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._up_btn.clicked.connect(lambda: self.stepBy(1))
        self._down_btn.clicked.connect(lambda: self.stepBy(-1))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = STEP_WIDTH
        height = max(9, (self.height() - 3) // 2)
        right = self.width() - width - 3
        self._up_btn.setGeometry(right, 2, width, height)
        self._down_btn.setGeometry(right, 2 + height, width, height)

    def wheelEvent(self, event) -> None:  # noqa: N802
        # wheel over the field should still change the value, as users expect
        super().wheelEvent(event)


class NumberBox(_Steppers, QSpinBox):
    def __init__(self, parent=None) -> None:
        QSpinBox.__init__(self, parent)
        self._install_steppers()


class DecimalBox(_Steppers, QDoubleSpinBox):
    def __init__(self, parent=None) -> None:
        QDoubleSpinBox.__init__(self, parent)
        self._install_steppers()
