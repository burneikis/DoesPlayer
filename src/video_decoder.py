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

    def get_frame_at_position(self, target_pts: float) -> Optional[VideoFrame]:
        """
        Get a single frame at or just after the target position.
        
        This performs a seek to the nearest keyframe before target_pts,
        then decodes forward until reaching the target frame.
        
        Args:
            target_pts: Target presentation timestamp in seconds
            
        Returns:
            VideoFrame at the target position, or None if not found
        """
        if not self.container or not self.video_stream:
            return None
        
        target_pts = max(0.0, min(target_pts, self.duration))
        
        try:
            # Create a separate container for frame-accurate seeking
            # This avoids interfering with the main decode thread
            with av.open(self.file_path) as seek_container:
                video_stream = None
                for stream in seek_container.streams:
                    if stream.type == 'video':
                        video_stream = stream
                        break
                
                if video_stream is None:
                    return None
                
                # Seek to keyframe before target
                target_ts = int(target_pts / video_stream.time_base)
                seek_container.seek(target_ts, stream=video_stream, backward=True)
                
                # Decode frames until we reach or pass the target
                last_frame = None
                frame_number = int(target_pts * self.fps)
                
                for frame in seek_container.decode(video=0):
                    pts = float(frame.pts * video_stream.time_base) if frame.pts else 0.0
                    
                    # Convert frame to RGB
                    rgb_frame = frame.to_ndarray(format='rgb24')
                    video_frame = VideoFrame(
                        image=rgb_frame,
                        pts=pts,
                        frame_number=int(pts * self.fps)
                    )
                    
                    # If this frame is at or past our target, return it
                    if pts >= target_pts - (0.5 / self.fps):
                        return video_frame
                    
                    last_frame = video_frame
                
                # If we ran out of frames, return the last one we found
                return last_frame
                
        except Exception as e:
            print(f"Error getting frame at position {target_pts}: {e}")
            return None

    @property
    def frame_duration(self) -> float:
        """Get duration of a single frame in seconds."""
        return 1.0 / self.fps if self.fps > 0 else 1.0 / DEFAULT_FPS
