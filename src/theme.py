"""Application-wide Qt theming.

The overlay paints itself (see overlay_widget.py); this module styles the
regular chrome — the Settings dialog, tray menu and message boxes — so the
Light/Dark choice applies everywhere, not just to the overlay.

Light theme uses Qt's native palette (empty stylesheet); Dark applies the QSS
below.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication

_DARK_QSS = """
QWidget { background-color: #1e1e1e; color: #e8e8e8; }
QDialog, QMainWindow { background-color: #1e1e1e; }
QTabWidget::pane { border: 1px solid #3a3a3a; }
QTabBar::tab {
    background: #2a2a2a; color: #cfcfcf;
    padding: 6px 14px; border: 1px solid #3a3a3a; border-bottom: none;
}
QTabBar::tab:selected { background: #3a3a3a; color: #ffffff; }
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {
    background-color: #2a2a2a; color: #e8e8e8;
    border: 1px solid #4a4a4a; border-radius: 4px; padding: 4px 6px;
}
QComboBox QAbstractItemView {
    background-color: #2a2a2a; color: #e8e8e8; selection-background-color: #3d6fa5;
}
QPushButton {
    background-color: #3a3a3a; color: #e8e8e8;
    border: 1px solid #4a4a4a; border-radius: 4px; padding: 5px 14px;
}
QPushButton:hover { background-color: #454545; }
QPushButton:pressed { background-color: #2f2f2f; }
QCheckBox { color: #e8e8e8; }
QProgressBar {
    background-color: #2a2a2a; border: 1px solid #4a4a4a;
    border-radius: 4px; text-align: center;
}
QProgressBar::chunk { background-color: #3d6fa5; border-radius: 3px; }
QMenu { background-color: #2a2a2a; color: #e8e8e8; border: 1px solid #4a4a4a; }
QMenu::item:selected { background-color: #3d6fa5; }
QToolTip { background-color: #2a2a2a; color: #e8e8e8; border: 1px solid #4a4a4a; }
"""


def apply_theme(app: QApplication | None, theme: str) -> None:
    """Apply the given theme ('dark' or 'light') to the whole application."""
    if app is None:
        return
    app.setStyleSheet(_DARK_QSS if theme == "dark" else "")
