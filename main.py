"""
DoesPlayer - Python Video Player

A high-performance video player supporting 1080p60 video and multitrack audio.
"""

import sys
import queue
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from src.video_decoder import VideoDecoder, VideoFrame
from src.audio_decoder import AudioManager
from src.sync import SyncController
from src.gui import MainPlayerWidget


class PlayerSignals(QObject):
    """Qt signals for cross-thread communication."""
    frame_ready = pyqtSignal(object)  # VideoFrame
    position_update = pyqtSignal(float)
    duration_update = pyqtSignal(float)
    fps_update = pyqtSignal(float)
    playback_ended = pyqtSignal()


class VideoPlayer:
    """
    Main video player controller.
    
    Coordinates video decoding, audio playback, and GUI updates.
    """
    
    def __init__(self, widget: MainPlayerWidget):
        self.widget = widget
        self.signals = PlayerSignals()
        
        self._file_path: Optional[str] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=60)
        
        self._video_decoder: Optional[VideoDecoder] = None
        self._audio_manager: Optional[AudioManager] = None
        self._sync_controller: Optional[SyncController] = None
        
        self._is_playing = False
        self._duration = 0.0
        self._fps = 30.0
        
        self._setup_connections()
    
    def _setup_connections(self):
        """Connect signals and slots."""
        # Widget signals
        self.widget.file_selected.connect(self.open_file)
        self.widget.controls.play_clicked.connect(self.play)
        self.widget.controls.pause_clicked.connect(self.pause)
        self.widget.controls.seek_requested.connect(self.seek)
        
        # Audio track controls
        self.widget.audio_panel.volume_changed.connect(self._on_volume_changed)
        self.widget.audio_panel.mute_toggled.connect(self._on_mute_toggled)
        
        # Internal signals
        self.signals.frame_ready.connect(self._on_frame_ready)
        self.signals.position_update.connect(self.widget.controls.set_position)
        self.signals.duration_update.connect(self.widget.controls.set_duration)
    
    def open_file(self, file_path: str):
        """Open a video file."""
        # Stop any existing playback
        self.stop()
        
        self._file_path = file_path
        self._frame_queue = queue.Queue(maxsize=60)
        
        # Initialize video decoder
        self._video_decoder = VideoDecoder(
            file_path=file_path,
            frame_queue=self._frame_queue,
            on_duration=self._on_duration_received,
            on_fps=self._on_fps_received,
        )
        
        if not self._video_decoder.open():
            print("Failed to open video file")
            return
        
        # Initialize audio manager
        self._audio_manager = AudioManager(file_path)
        tracks = self._audio_manager.discover_tracks()
        
        if tracks:
            self._audio_manager.initialize_all_tracks()
            self.widget.audio_panel.set_tracks(tracks)
        else:
            self.widget.audio_panel.clear()
        
        # Initialize sync controller
        self._sync_controller = SyncController(
            frame_queue=self._frame_queue,
            on_frame_ready=self._emit_frame,
            on_position_update=self._emit_position,
        )
        self._sync_controller.set_fps(self._fps)
        
        # Update UI
        self.widget.controls.set_duration(self._video_decoder.duration)
        self.widget.controls.set_position(0.0)
        self.widget.controls.set_playing(False)
        
        print(f"Opened: {file_path}")
        print(f"Resolution: {self._video_decoder.width}x{self._video_decoder.height}")
        print(f"Duration: {self._video_decoder.duration:.2f}s")
        print(f"FPS: {self._fps:.2f}")
        print(f"Audio tracks: {len(tracks)}")
    
    def play(self):
        """Start or resume playback."""
        if not self._video_decoder:
            return
        
        if not self._is_playing:
            self._is_playing = True
            
            # Start video decoder if not already running
            if not self._video_decoder.is_alive():
                self._video_decoder.start()
            else:
                self._video_decoder.resume()
            
            # Start audio
            if self._audio_manager:
                if not any(p.is_alive() for p in self._audio_manager.players.values()):
                    self._audio_manager.start_all()
                else:
                    self._audio_manager.resume_all()
            
            # Start sync controller
            if self._sync_controller:
                if not self._sync_controller._running:
                    self._sync_controller.start()
                else:
                    self._sync_controller.resume()
            
            self.widget.controls.set_playing(True)
    
    def pause(self):
        """Pause playback."""
        if self._is_playing:
            self._is_playing = False
            
            # Pause sync controller first to stop frame consumption
            if self._sync_controller:
                self._sync_controller.pause()
            
            # Then pause decoders
            if self._video_decoder:
                self._video_decoder.pause()
            
            if self._audio_manager:
                self._audio_manager.pause_all()
            
            self.widget.controls.set_playing(False)
    
    def seek(self, position: float):
        """Seek to a position in seconds."""
        if self._video_decoder:
            self._video_decoder.seek(position)
        
        if self._audio_manager:
            self._audio_manager.seek_all(position)
        
        if self._sync_controller:
            self._sync_controller.seek(position)
    
    def stop(self):
        """Stop playback and clean up."""
        self._is_playing = False
        
        if self._sync_controller:
            self._sync_controller.stop()
            self._sync_controller = None
        
        if self._video_decoder:
            self._video_decoder.stop()
            self._video_decoder = None
        
        if self._audio_manager:
            self._audio_manager.stop_all()
            self._audio_manager = None
        
        # Clear frame queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        
        self.widget.video_widget.clear()
        self.widget.controls.set_playing(False)
    
    def _on_duration_received(self, duration: float):
        """Handle duration info from decoder."""
        self._duration = duration
        self.signals.duration_update.emit(duration)
    
    def _on_fps_received(self, fps: float):
        """Handle FPS info from decoder."""
        self._fps = fps
        if self._sync_controller:
            self._sync_controller.set_fps(fps)
    
    def _emit_frame(self, frame: VideoFrame):
        """Emit frame signal (from sync thread)."""
        self.signals.frame_ready.emit(frame)
    
    def _emit_position(self, position: float):
        """Emit position update signal (from sync thread)."""
        self.signals.position_update.emit(position)
    
    def _on_frame_ready(self, frame: VideoFrame):
        """Handle frame ready signal (in main thread)."""
        self.widget.video_widget.display_frame(frame.image)
    
    def _on_volume_changed(self, track_id: int, volume: float):
        """Handle volume change for a track."""
        if self._audio_manager:
            self._audio_manager.set_track_volume(track_id, volume)
    
    def _on_mute_toggled(self, track_id: int, muted: bool):
        """Handle mute toggle for a track."""
        if self._audio_manager:
            self._audio_manager.set_track_muted(track_id, muted)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DoesPlayer")
        self.setMinimumSize(1024, 600)
        self.resize(1280, 720)
        
        # Set dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #3d3d3d;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -4px 0;
                background: #0078d4;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #1a8cff;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)
        
        # Create main widget
        self.player_widget = MainPlayerWidget()
        self.setCentralWidget(self.player_widget)
        
        # Create player controller
        self.player = VideoPlayer(self.player_widget)
    
    def closeEvent(self, event):
        """Handle window close."""
        self.player.stop()
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("DoesPlayer")
    
    window = MainWindow()
    window.show()
    
    # Open file from command line argument if provided
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if Path(file_path).exists():
            window.player.open_file(file_path)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
