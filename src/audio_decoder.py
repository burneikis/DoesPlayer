"""
Audio Decoder Module

Handles audio decoding and playback using PyAV and sounddevice.
Supports simultaneous playback of multiple audio tracks.
"""

import threading
import queue
import time
from dataclasses import dataclass
from typing import Optional, Dict, List
import av
import numpy as np
import sounddevice as sd

# Constants
PAUSE_POLL_INTERVAL = 0.05  # seconds
QUEUE_PUT_TIMEOUT = 0.02  # seconds
AUDIO_QUEUE_SIZE = 100
AUDIO_BLOCK_SIZE = 1024
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 2


@dataclass
class AudioChunk:
    """Container for decoded audio data."""
    data: np.ndarray  # Audio samples
    pts: float  # Presentation timestamp in seconds
    duration: float  # Duration of this chunk


class AudioTrackPlayer(threading.Thread):
    """
    Decodes and plays a single audio track.
    
    Each audio track runs in its own thread with its own sounddevice stream.
    """
    
    def __init__(
        self,
        file_path: str,
        stream_index: int,
        track_id: int,
        output_device: Optional[int] = None,
        buffer_duration: float = 0.5,
    ):
        super().__init__(daemon=True)
        self.file_path = file_path
        self.stream_index = stream_index
        self.track_id = track_id
        self.output_device = output_device
        self.buffer_duration = buffer_duration
        
        self._running = False
        self._paused = False
        self._finished = False  # Explicit end-of-stream flag
        self._volume = 1.0
        self._muted = False
        self._seek_requested = False
        self._seek_target = 0.0
        self._lock = threading.Lock()
        
        self.container: Optional[av.container.InputContainer] = None
        self.audio_stream = None
        self.sample_rate: int = DEFAULT_SAMPLE_RATE
        self.channels: int = DEFAULT_CHANNELS
        self.current_pts: float = 0.0
        
        # Audio buffer queue
        self._audio_queue: queue.Queue = queue.Queue(maxsize=AUDIO_QUEUE_SIZE)
        self._sd_stream: Optional[sd.OutputStream] = None
        
    def open(self) -> bool:
        """Open the audio stream."""
        try:
            self.container = av.open(self.file_path)
            
            # Find the specific audio stream
            audio_streams = [s for s in self.container.streams if s.type == 'audio']
            for stream in audio_streams:
                if stream.index == self.stream_index:
                    self.audio_stream = stream
                    break
            
            if self.audio_stream is None:
                print(f"Audio stream {self.stream_index} not found")
                return False
            
            self.sample_rate = self.audio_stream.sample_rate or DEFAULT_SAMPLE_RATE
            self.channels = self.audio_stream.channels or DEFAULT_CHANNELS
            
            # Limit channels to stereo for compatibility
            self.output_channels = min(self.channels, 2)
            
            return True
            
        except Exception as e:
            print(f"Error opening audio stream: {e}")
            return False
    
    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status):
        """Sounddevice callback - called from audio thread."""
        if status:
            print(f"Audio status: {status}")
        
        if self._paused:
            outdata.fill(0)
            return
        
        try:
            # Try to get audio data from queue
            chunk = self._audio_queue.get_nowait()
            
            # Apply volume
            data = chunk.data * self._volume
            
            # Handle mute by zeroing data, but still update current_pts
            if self._muted:
                outdata.fill(0)
            else:
                # Handle size mismatch
                if len(data) >= frames:
                    outdata[:] = data[:frames].reshape(-1, self.output_channels)
                else:
                    outdata[:len(data)] = data.reshape(-1, self.output_channels)
                    outdata[len(data):] = 0
            self.current_pts = chunk.pts
        except queue.Empty:
            outdata.fill(0)
    
    def run(self):
        """Main audio decoding loop."""
        if not self.container or not self.audio_stream:
            return
        
        self._running = True
        self._finished = False
        
        # Create resampler to convert to float32 planar
        resampler = av.audio.resampler.AudioResampler(
            format='fltp',
            layout='stereo' if self.output_channels == 2 else 'mono',
            rate=self.sample_rate
        )
        
        # Start sounddevice output stream
        try:
            self._sd_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.output_channels,
                dtype='float32',
                callback=self._audio_callback,
                blocksize=AUDIO_BLOCK_SIZE,
                device=self.output_device,
            )
            self._sd_stream.start()
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            return
        
        try:
            while self._running:
                # Handle pause - poll with timeout
                while self._paused and self._running:
                    time.sleep(PAUSE_POLL_INTERVAL)
                
                if not self._running:
                    break
                
                # Handle seek
                with self._lock:
                    if self._seek_requested:
                        self._perform_seek()
                        self._seek_requested = False
                        # Clear the audio queue
                        while not self._audio_queue.empty():
                            try:
                                self._audio_queue.get_nowait()
                            except queue.Empty:
                                break
                
                # Decode audio frames from our specific stream
                try:
                    for packet in self.container.demux(self.audio_stream):
                        if not self._running:
                            break
                        
                        # Check for seek during decode
                        with self._lock:
                            if self._seek_requested:
                                break
                        
                        for frame in packet.decode():
                            if not self._running:
                                break
                            
                            # Check pause - poll instead of blocking
                            while self._paused and self._running:
                                time.sleep(PAUSE_POLL_INTERVAL)
                            
                            if not self._running:
                                break
                            
                            # Resample frame
                            resampled = resampler.resample(frame)
                            
                            for res_frame in resampled:
                                # Convert to numpy array
                                audio_data = res_frame.to_ndarray()
                                
                                # Convert from planar to interleaved
                                if audio_data.ndim > 1:
                                    audio_data = audio_data.T.flatten()
                                
                                # Reshape for stereo
                                audio_data = audio_data.reshape(-1, self.output_channels)
                                
                                # Calculate PTS
                                pts = float(frame.pts * self.audio_stream.time_base) if frame.pts else 0.0
                                duration = len(audio_data) / self.sample_rate
                                
                                chunk = AudioChunk(
                                    data=audio_data.astype(np.float32),
                                    pts=pts,
                                    duration=duration
                                )
                                
                                # Wait for space in queue with pause checking
                                while self._running and not self._seek_requested and not self._paused:
                                    try:
                                        self._audio_queue.put(chunk, timeout=QUEUE_PUT_TIMEOUT)
                                        break
                                    except queue.Full:
                                        continue
                    else:
                        # End of stream
                        self._finished = True
                        self._running = False
                        break
                        
                except av.error.EOFError:
                    self._finished = True
                    self._running = False
                    break
                except Exception as e:
                    print(f"Audio decode error: {e}")
                    continue
                    
        finally:
            self._finished = True
            if self._sd_stream:
                self._sd_stream.stop()
                self._sd_stream.close()
            if self.container:
                self.container.close()
                self.container = None
    
    def _perform_seek(self):
        """Perform seek operation."""
        if self.container and self.audio_stream:
            target_ts = int(self._seek_target / self.audio_stream.time_base)
            try:
                self.container.seek(target_ts, stream=self.audio_stream)
            except Exception as e:
                print(f"Audio seek error: {e}")
    
    def seek(self, position: float):
        """Request a seek to the specified position."""
        with self._lock:
            self._seek_target = position
            self._seek_requested = True
    
    def pause(self):
        """Pause audio playback."""
        self._paused = True
    
    def resume(self):
        """Resume audio playback. Does nothing if at end of stream."""
        if not self._running:
            # At end of stream, do nothing
            return
        self._paused = False
    
    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
    
    def get_volume(self) -> float:
        """Get current volume."""
        return self._volume
    
    def set_muted(self, muted: bool):
        """Set mute state."""
        self._muted = muted
    
    def is_muted(self) -> bool:
        """Check if muted."""
        return self._muted
    
    @property
    def is_finished(self) -> bool:
        """Check if player has reached end of stream."""
        return self._finished and not self._running
    
    def stop(self):
        """Stop the audio player."""
        self._running = False
        self._paused = False  # Unblock if paused
        # Container cleanup is handled in the run() finally block
    
    def get_current_pts(self) -> float:
        """Get current playback position."""
        return self.current_pts


class AudioManager:
    """
    Manages multiple audio track players.
    
    Handles creation, synchronization, and control of all audio tracks.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.players: Dict[int, AudioTrackPlayer] = {}
        self._track_info: List[dict] = []
        
    def discover_tracks(self) -> List[dict]:
        """Discover all audio tracks in the file."""
        try:
            container = av.open(self.file_path)
            self._track_info = []
            
            for stream in container.streams:
                if stream.type == 'audio':
                    self._track_info.append({
                        'index': stream.index,
                        'channels': stream.channels,
                        'sample_rate': stream.sample_rate,
                        'codec': stream.codec_context.name if stream.codec_context else 'unknown',
                        'language': stream.language or f'Track {len(self._track_info) + 1}'
                    })
            
            container.close()
            return self._track_info
            
        except Exception as e:
            print(f"Error discovering tracks: {e}")
            return []
    
    def initialize_all_tracks(self) -> bool:
        """Initialize players for all audio tracks."""
        if not self._track_info:
            self.discover_tracks()
        
        for i, track in enumerate(self._track_info):
            player = AudioTrackPlayer(
                file_path=self.file_path,
                stream_index=track['index'],
                track_id=i,
            )
            if player.open():
                self.players[i] = player
            else:
                print(f"Failed to open track {i}")
        
        return len(self.players) > 0
    
    def start_all(self):
        """Start all audio players."""
        for player in self.players.values():
            player.start()
    
    def pause_all(self):
        """Pause all audio players."""
        for player in self.players.values():
            player.pause()
    
    def resume_all(self):
        """Resume all audio players."""
        for player in self.players.values():
            player.resume()
    
    def seek_all(self, position: float):
        """Seek all audio players to the same position."""
        for player in self.players.values():
            player.seek(position)
    
    def stop_all(self):
        """Stop all audio players."""
        for player in self.players.values():
            player.stop()
    
    def set_track_volume(self, track_id: int, volume: float):
        """Set volume for a specific track."""
        if track_id in self.players:
            self.players[track_id].set_volume(volume)
    
    def set_track_muted(self, track_id: int, muted: bool):
        """Set mute state for a specific track."""
        if track_id in self.players:
            self.players[track_id].set_muted(muted)
    
    def get_track_info(self) -> List[dict]:
        """Get info about all tracks."""
        return self._track_info
    
    def get_master_pts(self) -> float:
        """Get the PTS from the first track (used for sync reference)."""
        if 0 in self.players:
            return self.players[0].get_current_pts()
        return 0.0
