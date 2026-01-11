"""
Playback Synchronization Module

Handles synchronization between video and audio playback.
"""

import time
import threading
import queue
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class SyncState:
    """Current synchronization state."""
    video_pts: float = 0.0
    audio_pts: float = 0.0
    system_time: float = 0.0
    is_playing: bool = False
    playback_start_time: float = 0.0
    playback_start_pts: float = 0.0


class PlaybackClock:
    """
    Master playback clock for synchronization.
    
    Provides a consistent time reference for video and audio synchronization.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._is_running = False
        self._start_time = 0.0
        self._start_pts = 0.0
        self._current_pts = 0.0
        self._paused_at = 0.0
        
    def start(self, pts: float = 0.0):
        """Start the clock from the given PTS."""
        with self._lock:
            self._start_time = time.perf_counter()
            self._start_pts = pts
            self._current_pts = pts
            self._is_running = True
    
    def pause(self):
        """Pause the clock."""
        with self._lock:
            if self._is_running:
                self._paused_at = self.get_time()
                self._is_running = False
    
    def resume(self):
        """Resume the clock."""
        with self._lock:
            if not self._is_running:
                self._start_time = time.perf_counter()
                self._start_pts = self._paused_at
                self._is_running = True
    
    def seek(self, pts: float):
        """Seek to a new position."""
        with self._lock:
            self._start_pts = pts
            self._current_pts = pts
            if self._is_running:
                self._start_time = time.perf_counter()
            else:
                self._paused_at = pts
    
    def get_time(self) -> float:
        """Get current playback time in seconds."""
        with self._lock:
            if self._is_running:
                elapsed = time.perf_counter() - self._start_time
                return self._start_pts + elapsed
            else:
                return self._paused_at
    
    def is_running(self) -> bool:
        """Check if clock is running."""
        with self._lock:
            return self._is_running
    
    def stop(self):
        """Stop the clock."""
        with self._lock:
            self._is_running = False
            self._current_pts = 0.0


class SyncController:
    """
    Controls synchronization between video decoder and display.
    
    Uses a master clock to determine when frames should be displayed.
    """
    
    def __init__(
        self,
        frame_queue: queue.Queue,
        on_frame_ready: Optional[Callable] = None,
        on_position_update: Optional[Callable[[float], None]] = None,
    ):
        self.frame_queue = frame_queue
        self.on_frame_ready = on_frame_ready
        self.on_position_update = on_position_update
        
        self.clock = PlaybackClock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._fps = 60.0
        self._frame_duration = 1.0 / 60.0
        
        # Frame timing stats
        self._frames_displayed = 0
        self._frames_dropped = 0
        
    def set_fps(self, fps: float):
        """Set the target frame rate."""
        self._fps = fps
        self._frame_duration = 1.0 / fps
    
    def start(self, start_pts: float = 0.0):
        """Start the sync controller."""
        self._running = True
        self.clock.start(start_pts)
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
    
    def _sync_loop(self):
        """Main synchronization loop."""
        last_frame = None
        last_display_time = time.perf_counter()
        
        while self._running:
            # Check if paused - use short sleep to stay responsive
            if not self.clock.is_running():
                time.sleep(0.05)
                continue
            
            current_time = self.clock.get_time()
            
            # Try to get the next frame - short timeout to stay responsive to pause
            try:
                frame = self.frame_queue.get(timeout=0.05)
            except queue.Empty:
                # No frame available, check if still running
                if not self._running or not self.clock.is_running():
                    continue
                time.sleep(0.001)
                continue
            
            # Frame timing logic
            frame_pts = frame.pts
            
            # If frame is late, drop it and get the next one
            if frame_pts < current_time - self._frame_duration:
                self._frames_dropped += 1
                # Try to catch up
                while not self.frame_queue.empty() and self._running:
                    try:
                        next_frame = self.frame_queue.get_nowait()
                        if next_frame.pts >= current_time - self._frame_duration:
                            frame = next_frame
                            frame_pts = frame.pts
                            break
                        self._frames_dropped += 1
                    except queue.Empty:
                        break
            
            # Wait until it's time to display this frame
            display_time = frame_pts
            time_until_display = display_time - current_time
            
            if time_until_display > 0:
                # Sleep for most of the wait time
                if time_until_display > 0.005:
                    time.sleep(time_until_display - 0.002)
                # Busy wait for precise timing
                while self.clock.get_time() < display_time and self._running:
                    pass
            
            # Display the frame (check pause state again)
            if self.on_frame_ready and self._running and self.clock.is_running():
                self.on_frame_ready(frame)
                self._frames_displayed += 1
            
            # Update position callback
            if self.on_position_update and self._frames_displayed % 10 == 0 and self._running:
                self.on_position_update(frame_pts)
    
    def pause(self):
        """Pause playback."""
        self.clock.pause()
    
    def resume(self):
        """Resume playback."""
        self.clock.resume()
    
    def seek(self, pts: float):
        """Seek to a new position."""
        self.clock.seek(pts)
    
    def stop(self):
        """Stop the sync controller."""
        self._running = False
        self.clock.stop()
        if self._thread:
            self._thread.join(timeout=1.0)
    
    def get_stats(self) -> dict:
        """Get playback statistics."""
        return {
            'frames_displayed': self._frames_displayed,
            'frames_dropped': self._frames_dropped,
            'current_time': self.clock.get_time(),
        }
