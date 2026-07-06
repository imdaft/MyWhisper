from __future__ import annotations

import logging
from typing import Final

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

logger = logging.getLogger(__name__)

_ICON_SIZE: Final[int] = 32

_STATE_COLORS: Final[dict[str, QColor]] = {
    "idle": QColor(160, 160, 160),
    "recording": QColor(220, 40, 40),
    "processing": QColor(230, 160, 30),
}

_STATE_TOOLTIPS: Final[dict[str, str]] = {
    "idle": "MyWhisper - Idle",
    "recording": "MyWhisper - Recording...",
    "processing": "MyWhisper - Processing...",
}


def _create_microphone_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(color, 2.0)
    p.setPen(pen)
    p.setBrush(QBrush(color))

    # Microphone body: rounded rect centered horizontally
    body_w, body_h = 10, 16
    body_x = (_ICON_SIZE - body_w) // 2
    body_y = 2
    p.drawRoundedRect(body_x, body_y, body_w, body_h, 3.0, 3.0)

    # Stand line: vertical line from bottom of body to base
    center_x = _ICON_SIZE // 2
    stand_top = body_y + body_h + 1
    stand_bottom = stand_top + 5
    p.setPen(QPen(color, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(center_x, stand_top, center_x, stand_bottom)

    # Cradle arc: half-circle around the mic body
    arc_margin = 3
    arc_rect_x = body_x - arc_margin
    arc_rect_y = body_y + 2
    arc_rect_w = body_w + 2 * arc_margin
    arc_rect_h = body_h + 2
    p.drawArc(arc_rect_x, arc_rect_y, arc_rect_w, arc_rect_h, 0, -180 * 16)

    # Base line: horizontal at the bottom of the stand
    base_half = 5
    p.drawLine(center_x - base_half, stand_bottom, center_x + base_half, stand_bottom)

    p.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._status: str = "idle"
        self._last_text: str = ""
        self._icons: dict[str, QIcon] = {
            state: _create_microphone_icon(color)
            for state, color in _STATE_COLORS.items()
        }
        self._build_menu()
        self.setIcon(self._icons["idle"])
        self.setToolTip(_STATE_TOOLTIPS["idle"])
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        title_action = QAction("MyWhisper", menu)
        title_action.setEnabled(False)
        font = title_action.font()
        font.setBold(True)
        title_action.setFont(font)
        menu.addAction(title_action)

        menu.addSeparator()

        self._last_phrase_action = QAction("Last: (none)", menu)
        self._last_phrase_action.setEnabled(False)
        menu.addAction(self._last_phrase_action)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        about_action = QAction("About", menu)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def set_status(self, status: str) -> None:
        if status not in _STATE_COLORS:
            logger.warning("Unknown tray status: %s", status)
            return
        self._status = status
        self.setIcon(self._icons[status])
        self.setToolTip(_STATE_TOOLTIPS[status])

    def show_last_phrase(self, text: str) -> None:
        self._last_text = text
        display = text if len(text) <= 60 else text[:57] + "..."
        self._last_phrase_action.setText(f"Last: {display}")
        self.showMessage("MyWhisper", text, QSystemTrayIcon.MessageIcon.Information, 3000)

    def notify(self, title: str, message: str, level: str = "info") -> None:
        """Show a tray balloon notification (info / warning / error)."""
        icon = {
            "info": QSystemTrayIcon.MessageIcon.Information,
            "warning": QSystemTrayIcon.MessageIcon.Warning,
            "error": QSystemTrayIcon.MessageIcon.Critical,
        }.get(level, QSystemTrayIcon.MessageIcon.Information)
        self.showMessage(title, message, icon, 4000)

    @property
    def status(self) -> str:
        return self._status

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.settings_requested.emit()

    @staticmethod
    def _show_about() -> None:
        QMessageBox.about(
            None,  # type: ignore[arg-type]
            "About MyWhisper",
            "<b>MyWhisper</b><br><br>"
            "Local speech-to-text using Whisper.<br>"
            "Press your hotkey to record, release to transcribe.",
        )
