"""
Video Decoder Module

Handles video decoding using PyAV in a separate thread.
"""

import threading
import time
import queue
from dataclasses import dataclass
from typing import Optional, Callable
import av
import numpy as np
# Constants
PAUSE_POLL_INTERVAL = 0.05  # seconds
QUEUE_PUT_TIMEOUT = 0.02  # seconds
DEFAULT_FPS = 30.0
FRAME_CACHE_SIZE = 120  # Number of frames to cache for stepping

@dataclass
class VideoFrame:
    """Container for decoded video frame data."""
    image: np.ndarray  # RGB frame data
    pts: float  # Presentation timestamp in seconds
    frame_number: int


class VideoDecoder(threading.Thread):
    """
    Decodes video frames from a media file using PyAV.
    
    Runs in a separate thread and feeds frames to a queue for display.
    """
    
    def __init__(
        self,
        file_path: str,
        frame_queue: queue.Queue,
        buffer_size: int = 30,
        on_duration: Optional[Callable[[float], None]] = None,
        on_fps: Optional[Callable[[float], None]] = None,
    ):
        super().__init__(daemon=True)
        self.file_path = file_path
        self.frame_queue = frame_queue
        self.buffer_size = buffer_size
        self.on_duration = on_duration
        self.on_fps = on_fps
        
        self._running = False
        self._paused = False
        self._finished = False  # Explicit end-of-stream flag
        self._seek_requested = False
        self._seek_target = 0.0
        self._lock = threading.Lock()
        
        self.container: Optional[av.container.InputContainer] = None
        self.video_stream: Optional[av.video.stream.VideoStream] = None
        self.duration: float = 0.0
        self.fps: float = DEFAULT_FPS
        self.width: int = 0
        
        # Frame cache for efficient stepping
        self._frame_cache: list[VideoFrame] = []
        self._frame_cache_lock = threading.Lock()
        
        # Persistent container for frame stepping (avoids reopening file)
        self._step_container: Optional[av.container.InputContainer] = None
        self._step_stream: Optional[av.video.stream.VideoStream] = None
        self._step_decoder = None  # Generator for sequential decoding
        self._step_last_pts: float = -1.0
        self.height: int = 0
        
    def open(self) -> bool:
        """Open the video file and extract metadata."""
        try:
            self.container = av.open(self.file_path)
            
            # Find video stream
            for stream in self.container.streams:
                if stream.type == 'video':
                    self.video_stream = stream
                    break
            
            if self.video_stream is None:
                print("No video stream found")
                return False
            
            # Extract metadata
            self.duration = float(self.container.duration / av.time_base) if self.container.duration else 0.0
            self.fps = float(self.video_stream.average_rate) if self.video_stream.average_rate else 30.0
            self.width = self.video_stream.width
            self.height = self.video_stream.height
            
            # Set thread count for faster decoding
            self.video_stream.thread_type = "AUTO"
            
            if self.on_duration:
                self.on_duration(self.duration)
            if self.on_fps:
                self.on_fps(self.fps)
                
            return True
            
        except Exception as e:
            print(f"Error opening video: {e}")
            return False
    
    def run(self):
        """Main decoding loop."""
        if not self.container or not self.video_stream:
            return
            
        self._running = True
        self._finished = False
        frame_number = 0
        
        try:
            while self._running:
                # Handle pause - poll with timeout instead of blocking
                while self._paused and self._running:
                    time.sleep(PAUSE_POLL_INTERVAL)
                
                if not self._running:
                    break
                
                # Handle seek
                with self._lock:
                    if self._seek_requested:
                        self._perform_seek()
                        self._seek_requested = False
                        frame_number = int(self._seek_target * self.fps)
                        # Clear the queue after seeking
                        while not self.frame_queue.empty():
                            try:
                                self.frame_queue.get_nowait()
                            except queue.Empty:
                                break
                
                # Decode next frame
                try:
                    for frame in self.container.decode(video=0):
                        if not self._running:
                            break
                            
                        # Check for seek during decode
                        with self._lock:
                            if self._seek_requested:
                                break
                        
                        # Check pause - poll instead of blocking
                        while self._paused and self._running:
                            time.sleep(PAUSE_POLL_INTERVAL)
                        
                        if not self._running:
                            break
                        
                        # Convert frame to RGB numpy array
                        rgb_frame = frame.to_ndarray(format='rgb24')
                        
                        # Calculate presentation timestamp
                        pts = float(frame.pts * self.video_stream.time_base) if frame.pts else frame_number / self.fps
                        
                        video_frame = VideoFrame(
                            image=rgb_frame,
                            pts=pts,
                            frame_number=frame_number
                        )
                        
                        # Wait for space in queue with pause checking
                        while self._running and not self._seek_requested and not self._paused:
                            try:
                                self.frame_queue.put(video_frame, timeout=QUEUE_PUT_TIMEOUT)
                                break
                            except queue.Full:
                                continue
                        
                        frame_number += 1
                    else:
                        # End of stream reached
                        self._finished = True
                        self._running = False
                        break
                        
                except av.error.EOFError:
                    self._finished = True
                    self._running = False
                    break
                except Exception as e:
                    print(f"Decode error: {e}")
                    continue
                    
        finally:
            self._finished = True
    
    def _perform_seek(self):
        """Perform the actual seek operation."""
        if self.container and self.video_stream:
            # Convert seconds to stream time base
            target_ts = int(self._seek_target / self.video_stream.time_base)
            try:
                self.container.seek(target_ts, stream=self.video_stream)
            except Exception as e:
                print(f"Seek error: {e}")
    
    def seek(self, position: float):
        """Request a seek to the specified position in seconds."""
        with self._lock:
            self._seek_target = max(0.0, min(position, self.duration))
            self._seek_requested = True
            self._finished = False  # Reset finished flag on seek
    
    @property
    def is_finished(self) -> bool:
        """Check if decoder has reached end of stream."""
        return self._finished and not self._running
    
    def pause(self):
        """Pause video decoding."""
        self._paused = True
    
    def resume(self):
        """Resume video decoding. Does nothing if at end of stream."""
        if not self._running:
            # At end of stream, do nothing
            return
        self._paused = False
    
    def is_paused(self) -> bool:
        """Check if decoding is paused."""
        return self._paused
    
    def stop(self):
        """Stop the decoder thread."""
        self._running = False
        self._paused = False  # Unblock if paused
        if self.container:
            self.container.close()
        self._close_step_container()
        self.clear_frame_cache()
    
    def get_audio_tracks(self) -> list:
        """Get list of audio track info from the container."""
        tracks = []
        if self.container:
            for i, stream in enumerate(self.container.streams):
                if stream.type == 'audio':
                    tracks.append({
                        'index': stream.index,
                        'channels': stream.channels,
                        'sample_rate': stream.sample_rate,
                        'codec': stream.codec_context.name if stream.codec_context else 'unknown',
                        'language': stream.language or f'Track {len(tracks) + 1}'
                    })
        return tracks

    def _ensure_step_container(self):
        """Ensure the step container is open for frame stepping."""
        if self._step_container is None:
            self._step_container = av.open(self.file_path)
            for stream in self._step_container.streams:
                if stream.type == 'video':
                    self._step_stream = stream
                    break
            self._step_decoder = None
            self._step_last_pts = -1.0

    def _add_to_cache(self, frame: VideoFrame):
        """Add a frame to the cache, maintaining size limit."""
        with self._frame_cache_lock:
            # Check if frame already in cache
            for cached in self._frame_cache:
                if abs(cached.pts - frame.pts) < 0.001:
                    return
            
            self._frame_cache.append(frame)
            # Sort by pts
            self._frame_cache.sort(key=lambda f: f.pts)
            
            # Trim cache if too large
            while len(self._frame_cache) > FRAME_CACHE_SIZE:
                self._frame_cache.pop(0)

    def _get_from_cache(self, target_pts: float) -> Optional[VideoFrame]:
        """Try to get a frame from cache. Returns None if not found."""
        with self._frame_cache_lock:
            tolerance = 0.5 / self.fps
            for frame in self._frame_cache:
                if abs(frame.pts - target_pts) < tolerance:
                    return frame
        return None

    def _get_adjacent_from_cache(self, current_pts: float, direction: int) -> Optional[VideoFrame]:
        """Get the next or previous frame from cache relative to current position."""
        with self._frame_cache_lock:
            if not self._frame_cache:
                return None
            
            tolerance = 0.5 / self.fps
            
            if direction > 0:  # Forward
                # Find first frame after current
                for frame in self._frame_cache:
                    if frame.pts > current_pts + tolerance:
                        return frame
            else:  # Backward
                # Find last frame before current
                prev_frame = None
                for frame in self._frame_cache:
                    if frame.pts < current_pts - tolerance:
                        prev_frame = frame
                    else:
                        break
                return prev_frame
        return None

    def clear_frame_cache(self):
        """Clear the frame cache (call after seeking)."""
        with self._frame_cache_lock:
            self._frame_cache.clear()
        self._step_decoder = None
        self._step_last_pts = -1.0

    def get_frame_at_position(self, target_pts: float, current_pts: float = -1.0, direction: int = 0) -> Optional[VideoFrame]:
        """
        Get a single frame at or just after the target position.
        
        Uses caching and persistent container for efficient frame stepping.
        
        Args:
            target_pts: Target presentation timestamp in seconds
            current_pts: Current position (for smart cache lookup)
            direction: Step direction (1=forward, -1=backward, 0=seek)
            
        Returns:
            VideoFrame at the target position, or None if not found
        """
        if not self.container or not self.video_stream:
            return None
        
        target_pts = max(0.0, min(target_pts, self.duration))
        
        # First, try to get from cache if stepping
        if direction != 0 and current_pts >= 0:
            cached = self._get_adjacent_from_cache(current_pts, direction)
            if cached is not None:
                return cached
        
        # Also check if target is directly in cache
        cached = self._get_from_cache(target_pts)
        if cached is not None:
            return cached
        
        try:
            self._ensure_step_container()
            
            if self._step_stream is None:
                return None
            
            # Check if we can continue from last position (forward stepping)
            can_continue = (
                direction >= 0 and 
                self._step_decoder is not None and 
                self._step_last_pts >= 0 and
                target_pts > self._step_last_pts and
                target_pts - self._step_last_pts < 2.0  # Within 2 seconds
            )
            
            if not can_continue:
                # Need to seek - seek to keyframe before target
                target_ts = int(target_pts / self._step_stream.time_base)
                self._step_container.seek(target_ts, stream=self._step_stream, backward=True)
                self._step_decoder = self._step_container.decode(video=0)
            
            # Decode frames until we reach target
            tolerance = 0.5 / self.fps
            
            for frame in self._step_decoder:
                pts = float(frame.pts * self._step_stream.time_base) if frame.pts else 0.0
                self._step_last_pts = pts
                
                # Convert frame to RGB
                rgb_frame = frame.to_ndarray(format='rgb24')
                video_frame = VideoFrame(
                    image=rgb_frame,
                    pts=pts,
                    frame_number=int(pts * self.fps)
                )
                
                # Add to cache for future use
                self._add_to_cache(video_frame)
                
                # If this frame is at or past our target, return it
                if pts >= target_pts - tolerance:
                    return video_frame
            
            # Ran out of frames
            return None
                
        except Exception as e:
            print(f"Error getting frame at position {target_pts}: {e}")
            # Reset step container on error
            self._close_step_container()
            return None

    def _close_step_container(self):
        """Close the step container."""
        if self._step_container:
            try:
                self._step_container.close()
            except Exception:
                pass
            self._step_container = None
            self._step_stream = None
            self._step_decoder = None
            self._step_last_pts = -1.0

    @property
    def frame_duration(self) -> float:
        """Get duration of a single frame in seconds."""
        return 1.0 / self.fps if self.fps > 0 else 1.0 / DEFAULT_FPS
