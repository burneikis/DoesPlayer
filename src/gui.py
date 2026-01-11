"""
GUI Components Module

PyQt6-based widgets for the video player interface.
Incorporates notifications, audio mixer, keybinds, and overlays from GoodPlayer.
"""

from typing import Optional, Callable, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QFileDialog, QGroupBox, QScrollArea, QSizePolicy,
    QStyle, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor
import numpy as np


class NotificationOverlay(QLabel):
    """Overlay widget for showing action notifications."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: white;
            font-size: 18px;
            font-weight: bold;
            padding: 10px 20px;
            border-radius: 8px;
        """)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_notification(self, text: str, duration_ms: int = 1000) -> None:
        """Show a notification that fades after duration."""
        self.setText(text)
        self.adjustSize()
        # Position in top right of parent
        if self.parent():
            parent_rect = self.parent().rect()
            margin = 10
            self.move(
                parent_rect.width() - self.width() - margin,
                margin
            )
        self.show()
        self.raise_()
        self._timer.start(duration_ms)


class WelcomeOverlay(QLabel):
    """Overlay widget prompting user to open a file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Click here or press\nCtrl/Cmd+O to Open")
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 200);
                color: #aaaaaa;
                font-size: 20px;
                padding: 40px;
                border: 2px dashed #555555;
                border-radius: 12px;
            }
            QLabel:hover {
                color: #ffffff;
                border-color: #888888;
                background-color: rgba(0, 0, 0, 220);
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._click_callback = None

    def set_click_callback(self, callback):
        self._click_callback = callback

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._click_callback:
            self._click_callback()
        super().mousePressEvent(event)


class ClickableSlider(QSlider):
    """A slider that responds to mouse clicks anywhere on the track."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate value from click position
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            else:
                value = self.minimum() + (self.maximum() - self.minimum()) * (self.height() - event.position().y()) / self.height()
            self.setValue(int(value))
            self.sliderPressed.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sliderReleased.emit()
        super().mouseReleaseEvent(event)


class VideoWidget(QWidget):
    """
    Widget for displaying video frames.
    
    Efficiently renders numpy RGB arrays to a Qt widget.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: black;")
        
        self._current_image: Optional[QImage] = None
        self._aspect_ratio = 16 / 9
        
    def display_frame(self, frame: np.ndarray):
        """Display a numpy RGB frame."""
        if frame is None:
            return
        
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        
        # Create QImage from numpy array
        self._current_image = QImage(
            frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        ).copy()  # Copy to ensure data persists
        
        self._aspect_ratio = width / height
        self.update()
    
    def paintEvent(self, event):
        """Paint the current frame maintaining aspect ratio."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Fill background
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        if self._current_image:
            # Calculate target rectangle maintaining aspect ratio
            widget_ratio = self.width() / self.height()
            
            if widget_ratio > self._aspect_ratio:
                # Widget is wider - fit to height
                target_height = self.height()
                target_width = int(target_height * self._aspect_ratio)
            else:
                # Widget is taller - fit to width
                target_width = self.width()
                target_height = int(target_width / self._aspect_ratio)
            
            x = (self.width() - target_width) // 2
            y = (self.height() - target_height) // 2
            
            # Draw scaled image
            scaled_pixmap = QPixmap.fromImage(self._current_image).scaled(
                target_width, target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(x, y, scaled_pixmap)
        
        painter.end()
    
    def clear(self):
        """Clear the display."""
        self._current_image = None
        self.update()


class AudioTrackWidget(QFrame):
    """Widget for controlling a single audio track (vertical mixer style)."""

    def __init__(self, track_index: int, track_info: dict = None, parent=None):
        super().__init__(parent)
        self.track_index = track_index
        self.track_info = track_info or {}
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #3a3a3a; border-radius: 4px; padding: 5px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        # Track label
        label_text = self.track_info.get('language', f'Track {self.track_index + 1}')
        self._label = QLabel(label_text)
        self._label.setStyleSheet("color: white; font-weight: bold;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        # Volume slider (vertical)
        self._volume_slider = QSlider(Qt.Orientation.Vertical)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setMinimumHeight(80)
        self._volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self._volume_slider, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Volume label
        self._volume_label = QLabel("100%")
        self._volume_label.setStyleSheet("color: #aaa;")
        self._volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._volume_label)

        # Mute checkbox
        self._mute_checkbox = QCheckBox("Mute")
        self._mute_checkbox.setStyleSheet("color: white;")
        self._mute_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._mute_checkbox.stateChanged.connect(self._on_mute_changed)
        layout.addWidget(self._mute_checkbox, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._volume_callback = None
        self._mute_callback = None

    def set_volume_callback(self, callback):
        self._volume_callback = callback

    def set_mute_callback(self, callback):
        self._mute_callback = callback

    def _on_volume_changed(self, value: int):
        self._volume_label.setText(f"{value}%")
        if self._volume_callback:
            self._volume_callback(self.track_index, value / 100.0)

    def _on_mute_changed(self, state: int):
        if self._mute_callback:
            self._mute_callback(self.track_index, state == Qt.CheckState.Checked.value)

    def set_volume(self, volume: float):
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(int(volume * 100))
        self._volume_label.setText(f"{int(volume * 100)}%")
        self._volume_slider.blockSignals(False)


class AudioMixerPanel(QFrame):
    """Panel for audio mixing controls (hideable, vertical mixer style)."""

    volume_changed = pyqtSignal(int, float)  # track_id, volume
    mute_toggled = pyqtSignal(int, bool)  # track_id, muted

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track_widgets: List[AudioTrackWidget] = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #2b2b2b;")
        self.setFixedWidth(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header
        header = QLabel("Audio Mixer")
        header.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Scroll area for tracks
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._tracks_container = QWidget()
        self._tracks_layout = QVBoxLayout(self._tracks_container)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(5)
        self._tracks_layout.addStretch()

        scroll.setWidget(self._tracks_container)
        layout.addWidget(scroll)

        # Placeholder when no tracks
        self._no_tracks_label = QLabel("No audio\ntracks")
        self._no_tracks_label.setStyleSheet("color: #666;")
        self._no_tracks_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tracks_layout.insertWidget(0, self._no_tracks_label)

    def set_tracks(self, tracks: List[dict]):
        """Set up controls for all audio tracks."""
        # Clear existing widgets
        for widget in self._track_widgets:
            self._tracks_layout.removeWidget(widget)
            widget.deleteLater()
        self._track_widgets.clear()

        self._no_tracks_label.setVisible(len(tracks) == 0)

        for i, track in enumerate(tracks):
            track_widget = AudioTrackWidget(i, track)
            track_widget.set_volume_callback(self._on_volume_changed)
            track_widget.set_mute_callback(self._on_mute_changed)
            self._track_widgets.append(track_widget)
            self._tracks_layout.insertWidget(i, track_widget)

    def _on_volume_changed(self, track_index: int, volume: float):
        self.volume_changed.emit(track_index, volume)

    def _on_mute_changed(self, track_index: int, muted: bool):
        self.mute_toggled.emit(track_index, muted)

    def set_track_volume(self, track_index: int, volume: float):
        if 0 <= track_index < len(self._track_widgets):
            self._track_widgets[track_index].set_volume(volume)

    def clear(self):
        """Clear all track controls."""
        for widget in self._track_widgets:
            self._tracks_layout.removeWidget(widget)
            widget.deleteLater()
        self._track_widgets.clear()
        self._no_tracks_label.setVisible(True)


class PlayerControls(QWidget):
    """
    Playback control widget with seek bar.
    Uses clickable slider for easier seeking.
    """
    
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)  # Position in seconds
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_playing = False
        self._duration = 0.0
        self._seeking = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        
        # Timeline slider (clickable) - main control
        self.seek_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        self.seek_slider.sliderMoved.connect(self._on_seek_move)
        layout.addWidget(self.seek_slider)
    
    def _on_seek_start(self):
        self._seeking = True
    
    def _on_seek_end(self):
        self._seeking = False
        position = (self.seek_slider.value() / 1000.0) * self._duration
        self.seek_requested.emit(position)
    
    def _on_seek_move(self, value: int):
        pass  # Time display handled elsewhere
    
    def set_playing(self, playing: bool):
        """Update UI to reflect playing state."""
        self._is_playing = playing
    
    def set_duration(self, duration: float):
        """Set the total duration."""
        self._duration = duration
    
    def set_position(self, position: float):
        """Update the current position display."""
        if not self._seeking:
            if self._duration > 0:
                slider_value = int((position / self._duration) * 1000)
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(slider_value)
                self.seek_slider.blockSignals(False)


class MainPlayerWidget(QWidget):
    """
    Main player widget combining video display, controls, and audio mixer.
    Includes overlays for notifications and welcome screen.
    """
    
    file_selected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content area (video + mixer)
        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Video widget
        self.video_widget = VideoWidget()
        content_layout.addWidget(self.video_widget, stretch=1)

        # Audio mixer panel (right side, hidden by default)
        self.audio_panel = AudioMixerPanel()
        self.audio_panel.hide()
        content_layout.addWidget(self.audio_panel)

        main_layout.addWidget(content_area, stretch=1)

        # Welcome overlay (prompts user to open file)
        self._welcome_overlay = WelcomeOverlay(self.video_widget)
        self._welcome_overlay.set_click_callback(self._on_open_file)

        # Notification overlay (on top of video)
        self._notification = NotificationOverlay(self.video_widget)

        # Time info overlay (bottom left of video)
        self._time_label = QLabel("00:00.000 / 00:00.000", self.video_widget)
        self._time_label.setStyleSheet("color: white; font-family: monospace; background: transparent;")
        self._time_label.adjustSize()
        self._time_label.hide()

        # Controls panel
        self.controls = PlayerControls()
        self.controls.setStyleSheet("background-color: #2b2b2b;")
        main_layout.addWidget(self.controls)

    def _on_open_file(self):
        """Open file dialog to select a video file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All Files (*)"
        )
        if file_path:
            self.file_selected.emit(file_path)

    def show_notification(self, text: str, duration_ms: int = 800):
        """Show a notification overlay."""
        self._notification.show_notification(text, duration_ms)

    def hide_welcome(self):
        """Hide the welcome overlay and show time label."""
        self._welcome_overlay.hide()
        self._time_label.show()

    def show_welcome(self):
        """Show the welcome overlay and hide time label."""
        self._welcome_overlay.show()
        self._time_label.hide()

    def update_time_display(self, current_time: float, duration: float):
        """Update the time label."""
        def format_time(seconds: float) -> str:
            mins = int(seconds) // 60
            secs = seconds % 60
            return f"{mins:02d}:{secs:06.3f}"

        self._time_label.setText(f"{format_time(current_time)} / {format_time(duration)}")
        self._update_overlay_positions()

    def _update_overlay_positions(self):
        """Position overlays correctly."""
        margin = 10
        video_rect = self.video_widget.rect()

        # Time label - bottom left
        self._time_label.adjustSize()
        self._time_label.move(
            margin,
            video_rect.height() - self._time_label.height() - margin
        )

        # Welcome overlay - centered
        if self._welcome_overlay.isVisible():
            self._welcome_overlay.adjustSize()
            self._welcome_overlay.move(
                (video_rect.width() - self._welcome_overlay.width()) // 2,
                (video_rect.height() - self._welcome_overlay.height()) // 2
            )

    def resizeEvent(self, event):
        """Handle resize - reposition overlays."""
        super().resizeEvent(event)
        self._update_overlay_positions()

    def toggle_audio_mixer(self) -> bool:
        """Toggle audio mixer panel visibility. Returns new visibility state."""
        if self.audio_panel.isVisible():
            self.audio_panel.hide()
            return False
        else:
            self.audio_panel.show()
            return True
