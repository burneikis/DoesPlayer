"""
GUI Components Module

PyQt6-based widgets for the video player interface.
"""

from typing import Optional, Callable, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QFileDialog, QGroupBox, QScrollArea, QSizePolicy,
    QStyle, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor
import numpy as np


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


class TrackVolumeControl(QWidget):
    """
    Volume control widget for a single audio track.
    """
    
    volume_changed = pyqtSignal(int, float)  # track_id, volume
    mute_toggled = pyqtSignal(int, bool)  # track_id, muted
    
    def __init__(self, track_id: int, track_info: dict, parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self.track_info = track_info
        self._muted = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Track label
        label_text = self.track_info.get('language', f'Track {self.track_id + 1}')
        self.label = QLabel(f"{label_text}")
        self.label.setMinimumWidth(80)
        self.label.setStyleSheet("color: white;")
        layout.addWidget(self.label)
        
        # Mute button
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(30, 25)
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._on_mute_clicked)
        layout.addWidget(self.mute_btn)
        
        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMinimumWidth(100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.volume_slider)
        
        # Volume label
        self.volume_label = QLabel("100%")
        self.volume_label.setMinimumWidth(40)
        self.volume_label.setStyleSheet("color: white;")
        layout.addWidget(self.volume_label)
    
    def _on_volume_changed(self, value: int):
        self.volume_label.setText(f"{value}%")
        self.volume_changed.emit(self.track_id, value / 100.0)
    
    def _on_mute_clicked(self):
        self._muted = self.mute_btn.isChecked()
        self.mute_btn.setText("🔇" if self._muted else "🔊")
        self.mute_toggled.emit(self.track_id, self._muted)


class AudioTracksPanel(QWidget):
    """
    Panel containing volume controls for all audio tracks.
    """
    
    volume_changed = pyqtSignal(int, float)
    mute_toggled = pyqtSignal(int, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.track_controls: List[TrackVolumeControl] = []
        self._setup_ui()
    
    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        
        # Title
        title = QLabel("Audio Tracks")
        title.setStyleSheet("color: white; font-weight: bold;")
        self.layout.addWidget(title)
        
        # Container for track controls
        self.tracks_container = QWidget()
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 0, 0, 0)
        self.tracks_layout.setSpacing(2)
        
        self.layout.addWidget(self.tracks_container)
        self.layout.addStretch()
    
    def set_tracks(self, tracks: List[dict]):
        """Set up controls for all audio tracks."""
        # Clear existing controls
        for control in self.track_controls:
            control.deleteLater()
        self.track_controls.clear()
        
        # Create new controls
        for i, track in enumerate(tracks):
            control = TrackVolumeControl(i, track)
            control.volume_changed.connect(self.volume_changed.emit)
            control.mute_toggled.connect(self.mute_toggled.emit)
            self.tracks_layout.addWidget(control)
            self.track_controls.append(control)
    
    def clear(self):
        """Clear all track controls."""
        for control in self.track_controls:
            control.deleteLater()
        self.track_controls.clear()


class PlayerControls(QWidget):
    """
    Playback control widget with play/pause, seek bar, and time display.
    """
    
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)  # Position in seconds
    open_file_clicked = pyqtSignal()
    
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
        
        # Seek bar and time display
        seek_layout = QHBoxLayout()
        
        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet("color: white; font-family: monospace;")
        seek_layout.addWidget(self.time_label)
        
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        self.seek_slider.sliderMoved.connect(self._on_seek_move)
        seek_layout.addWidget(self.seek_slider, stretch=1)
        
        self.duration_label = QLabel("00:00:00")
        self.duration_label.setStyleSheet("color: white; font-family: monospace;")
        seek_layout.addWidget(self.duration_label)
        
        layout.addLayout(seek_layout)
        
        # Control buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        self.open_btn = QPushButton("📂 Open")
        self.open_btn.clicked.connect(self.open_file_clicked.emit)
        buttons_layout.addWidget(self.open_btn)
        
        buttons_layout.addStretch()
        
        self.play_btn = QPushButton("▶️ Play")
        self.play_btn.setMinimumWidth(100)
        self.play_btn.clicked.connect(self._on_play_clicked)
        buttons_layout.addWidget(self.play_btn)
        
        buttons_layout.addStretch()
        
        layout.addLayout(buttons_layout)
    
    def _on_play_clicked(self):
        if self._is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()
    
    def _on_seek_start(self):
        self._seeking = True
    
    def _on_seek_end(self):
        self._seeking = False
        position = (self.seek_slider.value() / 1000.0) * self._duration
        self.seek_requested.emit(position)
    
    def _on_seek_move(self, value: int):
        position = (value / 1000.0) * self._duration
        self.time_label.setText(self._format_time(position))
    
    def set_playing(self, playing: bool):
        """Update UI to reflect playing state."""
        self._is_playing = playing
        self.play_btn.setText("⏸️ Pause" if playing else "▶️ Play")
    
    def set_duration(self, duration: float):
        """Set the total duration."""
        self._duration = duration
        self.duration_label.setText(self._format_time(duration))
    
    def set_position(self, position: float):
        """Update the current position display."""
        if not self._seeking:
            self.time_label.setText(self._format_time(position))
            if self._duration > 0:
                slider_value = int((position / self._duration) * 1000)
                self.seek_slider.setValue(slider_value)
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class MainPlayerWidget(QWidget):
    """
    Main player widget combining video display, controls, and audio track panel.
    """
    
    file_selected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left side - Video and controls
        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #1e1e1e;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Video widget
        self.video_widget = VideoWidget()
        left_layout.addWidget(self.video_widget, stretch=1)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #333;")
        left_layout.addWidget(separator)
        
        # Player controls
        self.controls = PlayerControls()
        self.controls.setStyleSheet("background-color: #2d2d2d;")
        self.controls.open_file_clicked.connect(self._on_open_file)
        left_layout.addWidget(self.controls)
        
        main_layout.addWidget(left_panel, stretch=1)
        
        # Right side - Audio tracks panel
        self.audio_panel = AudioTracksPanel()
        self.audio_panel.setFixedWidth(250)
        self.audio_panel.setStyleSheet("background-color: #252525;")
        main_layout.addWidget(self.audio_panel)
    
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
