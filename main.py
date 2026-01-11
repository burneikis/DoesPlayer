"""
DoesPlayer - Python Video Player

A high-performance video player supporting 1080p60 video and multitrack audio.
Features: notifications, keyboard controls, audio mixer panel.
"""

import sys
import time
import queue
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent, QPalette, QColor

from src.video_decoder import VideoDecoder, VideoFrame
from src.audio_decoder import AudioManager
from src.gui import MainPlayerWidget


class VideoPlayer:
    """
    Main video player controller.
    
    Coordinates video decoding, audio playback, and GUI updates.
    Uses a QTimer to pull frames from queue (avoids cross-thread signal issues).
    """
    
    def __init__(self, widget: MainPlayerWidget):
        self.widget = widget
        
        self._file_path: Optional[str] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=60)
        
        self._video_decoder: Optional[VideoDecoder] = None
        self._audio_manager: Optional[AudioManager] = None
        
        self._is_playing = False
        self._duration = 0.0
        self._fps = 30.0
        
        # Master volume for all tracks
        self._master_volume = 1.0
        
        # Playback timing
        self._playback_start_time = 0.0
        self._playback_start_pts = 0.0
        self._current_pts = 0.0
        self._last_frame: Optional[VideoFrame] = None
        self._pending_frame: Optional[VideoFrame] = None
        
        # Frame display timer - runs on main thread
        self._display_timer = QTimer()
        self._display_timer.timeout.connect(self._on_display_tick)
        
        # Position update timer
        self._position_timer = QTimer()
        self._position_timer.timeout.connect(self._update_position_display)
        self._position_timer.setInterval(100)  # Update every 100ms
        
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
        
        # Hide welcome overlay, show time display
        self.widget.hide_welcome()
        
        # Update UI
        self.widget.controls.set_duration(self._video_decoder.duration)
        self.widget.controls.set_position(0.0)
        self.widget.controls.set_playing(False)
        self.widget.update_time_display(0.0, self._video_decoder.duration)
        
        # Set timer interval based on FPS (poll faster than frame rate for smoothness)
        frame_interval = max(1, int(1000 / self._fps / 2))
        self._display_timer.setInterval(frame_interval)
        
        print(f"Opened: {file_path}")
        print(f"Resolution: {self._video_decoder.width}x{self._video_decoder.height}")
        print(f"Duration: {self._video_decoder.duration:.2f}s")
        print(f"FPS: {self._fps:.2f}")
        print(f"Audio tracks: {len(tracks)}")
    
    def _get_playback_time(self) -> float:
        """Get current playback time based on system clock."""
        if not self._is_playing:
            return self._current_pts
        elapsed = time.perf_counter() - self._playback_start_time
        return self._playback_start_pts + elapsed
    
    def play(self):
        """Start or resume playback. Does nothing if at end of stream."""
        if not self._video_decoder:
            return


        # Only block play/resume if at end of stream AND current position is at or beyond duration
        at_end = (
            not self._video_decoder.is_alive()
            and hasattr(self._video_decoder, '_running')
            and not self._video_decoder._running
            and hasattr(self._video_decoder, 'duration')
            and self._current_pts >= getattr(self._video_decoder, 'duration', float('inf')) - 0.01
        )
        if at_end:
            return

        if not self._is_playing:
            self._is_playing = True

            # Start video decoder if not already running
            if not self._video_decoder.is_alive():
                self._video_decoder.start()
                # Give decoder time to buffer initial frames
                QTimer.singleShot(100, self._start_playback)
            else:
                self._video_decoder.resume()
                self._start_playback()
    
    def _start_playback(self):
        """Actually start playback after decoder is ready."""
        if not self._is_playing:
            return
            
        # Set up timing
        self._playback_start_time = time.perf_counter()
        self._playback_start_pts = self._current_pts
        
        # Start audio
        if self._audio_manager and self._audio_manager.players:
            # Check if audio threads need to be restarted
            # A thread that's not alive but has ident set means it ran and finished
            needs_restart = any(
                not p.is_alive() and p.ident is not None
                for p in self._audio_manager.players.values()
            )
            
            if needs_restart:
                # Recreate audio manager since threads can't be restarted
                file_path = self._audio_manager.file_path
                self._audio_manager.stop_all()
                self._audio_manager = AudioManager(file_path)
                tracks = self._audio_manager.discover_tracks()
                if tracks:
                    self._audio_manager.initialize_all_tracks()
                    self._audio_manager.seek_all(self._current_pts)
                    self._audio_manager.start_all()
            elif not any(p.is_alive() for p in self._audio_manager.players.values()):
                self._audio_manager.start_all()
            else:
                self._audio_manager.resume_all()
        
        # Start display timer
        self._display_timer.start()
        self._position_timer.start()
        
        self.widget.controls.set_playing(True)
    
    def pause(self):
        """Pause playback."""
        if self._is_playing:
            self._is_playing = False
            
            # Stop timers first
            self._display_timer.stop()
            self._position_timer.stop()
            
            # Save current position
            self._current_pts = self._get_playback_time()
            
            # Pause decoders
            if self._video_decoder:
                self._video_decoder.pause()
            
            if self._audio_manager:
                self._audio_manager.pause_all()
            
            self.widget.controls.set_playing(False)
    
    def seek(self, position: float):
        """Seek to a position in seconds."""
        self._current_pts = position
        self._playback_start_pts = position
        self._playback_start_time = time.perf_counter()
        self._pending_frame = None
        
        # Clear frame queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        
        if self._video_decoder:
            # Check if decoder thread has stopped (e.g., reached end of video)
            # If so, we need to create a new decoder since threads can't be restarted
            if not self._video_decoder.is_alive():
                # Store the file path before stopping
                file_path = self._video_decoder.file_path
                self._video_decoder.stop()
                
                # Create a new decoder
                self._frame_queue = queue.Queue(maxsize=60)
                self._video_decoder = VideoDecoder(
                    file_path=file_path,
                    frame_queue=self._frame_queue,
                    on_duration=self._on_duration_received,
                    on_fps=self._on_fps_received,
                )
                self._video_decoder.open()
                self._video_decoder.seek(position)
                
                # Also recreate audio manager since its threads can't be restarted either
                if self._audio_manager:
                    self._audio_manager.stop_all()
                    self._audio_manager = AudioManager(file_path)
                    tracks = self._audio_manager.discover_tracks()
                    if tracks:
                        self._audio_manager.initialize_all_tracks()
                        # Seek audio to the same position
                        self._audio_manager.seek_all(position)
                
                # Start the new decoder if we're playing
                if self._is_playing:
                    self._video_decoder.start()
                    if self._audio_manager:
                        self._audio_manager.start_all()
            else:
                self._video_decoder.seek(position)
                if self._audio_manager:
                    self._audio_manager.seek_all(position)
        elif self._audio_manager:
            self._audio_manager.seek_all(position)
        
        self.widget.controls.set_position(position)
    
    def stop(self):
        """Stop playback and clean up."""
        self._is_playing = False
        
        # Stop timers
        self._display_timer.stop()
        self._position_timer.stop()
        
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
        
        self._current_pts = 0.0
        self._last_frame = None
        self._pending_frame = None
        self.widget.video_widget.clear()
        self.widget.controls.set_playing(False)
    
    def _on_display_tick(self):
        """Called by timer to display next frame."""
        if not self._is_playing:
            return
        
        current_time = self._get_playback_time()
        frame_to_display = None
        
        # First check if we have a pending frame from last tick that's now ready
        if self._pending_frame is not None:
            if self._pending_frame.pts <= current_time:
                frame_to_display = self._pending_frame
                self._pending_frame = None
            else:
                # Pending frame still not ready, don't pull more from queue
                return
        
        # Get frames from queue
        while True:
            try:
                frame = self._frame_queue.get_nowait()
                
                if frame.pts <= current_time:
                    # This frame should be displayed (or skipped if we find a newer one)
                    frame_to_display = frame
                else:
                    # This frame is for the future - save it for later
                    self._pending_frame = frame
                    break
                    
            except queue.Empty:
                break
        
        # Display the frame if we have one
        if frame_to_display is not None:
            self.widget.video_widget.display_frame(frame_to_display.image)
            self._current_pts = frame_to_display.pts
    
    def _update_position_display(self):
        """Update the position display in UI."""
        if self._is_playing:
            current_time = self._get_playback_time()
            
            # Check if we've reached the end of the video
            if current_time >= self._duration:
                current_time = self._duration
                self.pause()
                self.widget.controls.set_position(self._duration)
                self.widget.update_time_display(self._duration, self._duration)
                return
            
            self.widget.controls.set_position(current_time)
            self.widget.update_time_display(current_time, self._duration)
    
    def _on_duration_received(self, duration: float):
        """Handle duration info from decoder."""
        self._duration = duration
    
    def _on_fps_received(self, fps: float):
        """Handle FPS info from decoder."""
        self._fps = fps
        frame_interval = max(1, int(1000 / fps / 2))
        self._display_timer.setInterval(frame_interval)
    
    def _on_volume_changed(self, track_id: int, volume: float):
        """Handle volume change for a track."""
        if self._audio_manager:
            self._audio_manager.set_track_volume(track_id, volume)
    
    def _on_mute_toggled(self, track_id: int, muted: bool):
        """Handle mute toggle for a track."""
        if self._audio_manager:
            self._audio_manager.set_track_muted(track_id, muted)

    def toggle_playback(self):
        """Toggle play/pause state."""
        if self._is_playing:
            self.pause()
            self.widget.show_notification("Pause", 600)
        else:
            self.play()
            self.widget.show_notification("Play", 600)

    def change_volume(self, delta: float):
        """Change master volume by delta amount."""
        if not self._audio_manager:
            return
        new_volume = self._master_volume + delta
        # Round to nearest 5% to avoid floating-point precision issues
        self._master_volume = max(0.0, min(1.0, round(new_volume * 20) / 20))
        # Apply to all audio tracks
        for i in range(len(self._audio_manager.players)):
            self._audio_manager.set_track_volume(i, self._master_volume)
            self.widget.audio_panel.set_track_volume(i, self._master_volume)
        self.widget.show_notification(f"Volume: {int(self._master_volume * 100)}%", 600)

    def skip_time(self, seconds: float):
        """Skip forward or backward by the given number of seconds."""
        if not self._video_decoder:
            return
        new_time = max(0.0, min(self._duration, self._get_playback_time() + seconds))
        self.seek(new_time)
        sign = "+" if seconds > 0 else ""
        self.widget.show_notification(f"Skip {sign}{int(seconds)}s", 600)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def has_file(self) -> bool:
        return self._video_decoder is not None


class MainWindow(QMainWindow):
    """Main application window with keyboard controls."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DoesPlayer")
        self.setMinimumSize(800, 600)
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
        
        # Focus policy for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def _open_file(self):
        """Open a video file via dialog."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All Files (*)"
        )
        if filepath:
            self.player.open_file(filepath)
            self.setWindowTitle(f"DoesPlayer - {filepath}")

    def _toggle_audio_mixer(self):
        """Toggle audio mixer panel visibility."""
        visible = self.player_widget.toggle_audio_mixer()
        self.player_widget.show_notification("Mixer: On" if visible else "Mixer: Off", 600)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input."""
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+O / Cmd+O to open file (works without file loaded)
        if key == Qt.Key.Key_O and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self._open_file()
            return

        # A to toggle audio mixer (works without file loaded)
        if key == Qt.Key.Key_A:
            self._toggle_audio_mixer()
            return

        # The rest require a file to be loaded
        if not self.player.has_file:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Space:
            self.player.toggle_playback()
        elif key == Qt.Key.Key_Up:
            self.player.change_volume(0.05)
        elif key == Qt.Key.Key_Down:
            self.player.change_volume(-0.05)
        elif key == Qt.Key.Key_BracketLeft:
            self.player.skip_time(-5)  # [ = 5s back
        elif key == Qt.Key.Key_BracketRight:
            self.player.skip_time(10)  # ] = 10s forward
        elif key == Qt.Key.Key_BraceLeft:
            self.player.skip_time(-15)  # { = 15s back (Shift+[)
        elif key == Qt.Key.Key_BraceRight:
            self.player.skip_time(30)  # } = 30s forward (Shift+])
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Handle window close."""
        self.player.stop()
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("DoesPlayer")
    app.setStyle("Fusion")
    
    # Dark theme palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    
    # Open file from command line argument if provided
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if Path(file_path).exists():
            window.player.open_file(file_path)
            window.setWindowTitle(f"DoesPlayer - {file_path}")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
