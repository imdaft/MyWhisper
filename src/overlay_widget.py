from __future__ import annotations

import logging
import time
from typing import ClassVar

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

logger = logging.getLogger(__name__)

_WIDGET_WIDTH: int = 280
_WIDGET_HEIGHT: int = 70
_CORNER_RADIUS: float = 20.0
_BG_COLOR: QColor = QColor(30, 30, 30, 220)

_INDICATOR_RADIUS: float = 6.0
_INDICATOR_X: float = 24.0
_INDICATOR_Y: float = 26.0

_STATUS_FONT_SIZE: int = 14
_TIMER_FONT_SIZE: int = 11

_VU_HEIGHT: float = 6.0
_VU_Y: float = 48.0
_VU_LEFT: float = 44.0
_VU_RIGHT_MARGIN: float = 16.0
_VU_MAX_WIDTH: float = _WIDGET_WIDTH - _VU_LEFT - _VU_RIGHT_MARGIN
_VU_CORNER: float = 3.0

_LERP_FACTOR: float = 0.25

_PULSE_DURATION_MS: int = 1000
_TIMER_INTERVAL_MS: int = 100
_FADE_DURATION_MS: int = 150

_POSITION_MARGIN: int = 40


class OverlayWidget(QWidget):
    _POSITION_NAMES: ClassVar[list[str]] = [
        "bottom_center",
        "top_center",
        "top_right",
        "top_left",
        "bottom_right",
        "bottom_left",
    ]

    def __init__(self, position: str = "bottom_center", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._setup_window_flags()
        self.setFixedSize(QSize(_WIDGET_WIDTH, _WIDGET_HEIGHT))

        self._status_text: str = "Recording..."
        self._recording_seconds: float = 0.0
        self._record_start: float = 0.0
        self._current_level: float = 0.0
        self._display_level: float = 0.0
        self._indicator_color: QColor = QColor(Qt.GlobalColor.red)
        self._indicator_pulsing: bool = False
        self._pulse_opacity: float = 1.0
        self._position_name: str = position

        self._opacity_effect: QGraphicsOpacityEffect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._pulse_anim: QPropertyAnimation = self._create_pulse_animation()
        self._fade_anim: QPropertyAnimation = self._create_fade_animation()

        self._tick_timer: QTimer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(_TIMER_INTERVAL_MS)
        self._tick_timer.timeout.connect(self._on_tick)

    def _setup_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    # ------------------------------------------------------------------
    # Animated properties
    # ------------------------------------------------------------------

    def _get_pulse_opacity(self) -> float:
        return self._pulse_opacity

    def _set_pulse_opacity(self, value: float) -> None:
        self._pulse_opacity = value
        self.update()

    pulseOpacity = pyqtProperty(float, fget=_get_pulse_opacity, fset=_set_pulse_opacity)

    def _get_window_opacity(self) -> float:
        return self._opacity_effect.opacity()

    def _set_window_opacity(self, value: float) -> None:
        self._opacity_effect.setOpacity(value)

    windowOpacity = pyqtProperty(float, fget=_get_window_opacity, fset=_set_window_opacity)

    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------

    def _create_pulse_animation(self) -> QPropertyAnimation:
        anim = QPropertyAnimation(self, b"pulseOpacity", self)
        anim.setDuration(_PULSE_DURATION_MS)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)
        return anim

    def _create_fade_animation(self) -> QPropertyAnimation:
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(_FADE_DURATION_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        return anim

    def _fade_in(self) -> None:
        self._fade_anim.stop()
        self._disconnect_fade_finished()
        self._opacity_effect.setOpacity(0.0)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _fade_out(self) -> None:
        self._fade_anim.stop()
        self._disconnect_fade_finished()
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_finished)
        self._fade_anim.start()

    def _disconnect_fade_finished(self) -> None:
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass

    @pyqtSlot()
    def _on_fade_out_finished(self) -> None:
        self.hide()
        self._opacity_effect.setOpacity(1.0)
        self._disconnect_fade_finished()

    # ------------------------------------------------------------------
    # Tick / timer
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_tick(self) -> None:
        if self._record_start > 0.0:
            self._recording_seconds = time.monotonic() - self._record_start

        self._display_level += (self._current_level - self._display_level) * _LERP_FACTOR
        self.update()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_recording(self) -> None:
        logger.debug("Overlay: show_recording")
        self._status_text = "Recording..."
        self._indicator_color = QColor(Qt.GlobalColor.red)
        self._indicator_pulsing = True
        self._record_start = time.monotonic()
        self._recording_seconds = 0.0
        self._current_level = 0.0
        self._display_level = 0.0

        self._apply_position()
        self.show()
        self._fade_in()
        self._pulse_anim.start()
        self._tick_timer.start()

    def show_processing(self) -> None:
        logger.debug("Overlay: show_processing")
        self._status_text = "Processing..."
        self._indicator_color = QColor(255, 200, 0)
        self._indicator_pulsing = False
        self._pulse_opacity = 1.0
        self._pulse_anim.stop()
        self._current_level = 0.0
        self.update()

    def hide_overlay(self) -> None:
        logger.debug("Overlay: hide_overlay")
        self._tick_timer.stop()
        self._pulse_anim.stop()
        self._record_start = 0.0
        self._fade_out()

    def update_level(self, level: float) -> None:
        self._current_level = max(0.0, min(1.0, level))

    def set_position(self, position: str) -> None:
        if position not in self._POSITION_NAMES:
            logger.warning("Unknown overlay position %r, falling back to bottom_center", position)
            position = "bottom_center"
        self._position_name = position
        if self.isVisible():
            self._apply_position()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _apply_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo: QRect = screen.availableGeometry()
        w: int = self.width()
        h: int = self.height()
        margin: int = _POSITION_MARGIN

        positions: dict[str, tuple[int, int]] = {
            "bottom_center": (
                geo.x() + (geo.width() - w) // 2,
                geo.y() + geo.height() - h - margin,
            ),
            "top_center": (
                geo.x() + (geo.width() - w) // 2,
                geo.y() + margin,
            ),
            "top_right": (
                geo.x() + geo.width() - w - margin,
                geo.y() + margin,
            ),
            "top_left": (
                geo.x() + margin,
                geo.y() + margin,
            ),
            "bottom_right": (
                geo.x() + geo.width() - w - margin,
                geo.y() + geo.height() - h - margin,
            ),
            "bottom_left": (
                geo.x() + margin,
                geo.y() + geo.height() - h - margin,
            ),
        }

        x, y = positions.get(self._position_name, positions["bottom_center"])
        self.move(x, y)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._paint_background(painter)
        self._paint_indicator(painter)
        self._paint_status_text(painter)
        self._paint_timer(painter)
        self._paint_vu_meter(painter)

        painter.end()

    def _paint_background(self, painter: QPainter) -> None:
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, self.width(), self.height()),
            _CORNER_RADIUS,
            _CORNER_RADIUS,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BG_COLOR)
        painter.drawPath(path)

    def _paint_indicator(self, painter: QPainter) -> None:
        color = QColor(self._indicator_color)
        if self._indicator_pulsing:
            alpha = int(255 * self._pulse_opacity)
            color.setAlpha(alpha)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(
            QRectF(
                _INDICATOR_X - _INDICATOR_RADIUS,
                _INDICATOR_Y - _INDICATOR_RADIUS,
                _INDICATOR_RADIUS * 2,
                _INDICATOR_RADIUS * 2,
            )
        )

    def _paint_status_text(self, painter: QPainter) -> None:
        font = QFont("Segoe UI", _STATUS_FONT_SIZE)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255, 240)))

        text_rect = QRectF(44, 8, _WIDGET_WIDTH - 44 - 60, 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._status_text)

    def _paint_timer(self, painter: QPainter) -> None:
        total_seconds = int(self._recording_seconds)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        timer_str = f"{minutes}:{seconds:02d}"

        font = QFont("Segoe UI", _TIMER_FONT_SIZE)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QPen(QColor(180, 180, 180, 200)))

        text_rect = QRectF(_WIDGET_WIDTH - 60, 8, 48, 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, timer_str)

    def _paint_vu_meter(self, painter: QPainter) -> None:
        level = max(0.0, min(1.0, self._display_level))
        bar_width = level * _VU_MAX_WIDTH
        if bar_width < 1.0:
            return

        bar_rect = QRectF(_VU_LEFT, _VU_Y, bar_width, _VU_HEIGHT)

        gradient = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
        gradient.setColorAt(0.0, QColor(76, 175, 80))
        gradient.setColorAt(0.7, QColor(139, 195, 74))
        gradient.setColorAt(1.0, QColor(255, 235, 59))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)

        vu_path = QPainterPath()
        vu_path.addRoundedRect(bar_rect, _VU_CORNER, _VU_CORNER)
        painter.drawPath(vu_path)

        bg_rect = QRectF(_VU_LEFT + bar_width, _VU_Y, _VU_MAX_WIDTH - bar_width, _VU_HEIGHT)
        if bg_rect.width() > 0:
            painter.setBrush(QColor(60, 60, 60, 120))
            bg_path = QPainterPath()
            bg_path.addRoundedRect(bg_rect, _VU_CORNER, _VU_CORNER)
            painter.drawPath(bg_path)

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_WIDGET_WIDTH, _WIDGET_HEIGHT)
