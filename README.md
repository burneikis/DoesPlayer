# DoesPlayer

A high-performance video player built in Python supporting 1080p60 video and simultaneous multitrack audio playback.

## Features

- **Video Playback**: Smooth 1080p60 video playback using PyAV for decoding
- **Multitrack Audio**: Play all audio tracks simultaneously with independent volume controls
- **Modern GUI**: Dark-themed PyQt6 interface with intuitive controls
- **Efficient**: Multithreaded architecture for optimal performance

## Requirements

- Python 3.10+
- macOS, Linux, or Windows

## Installation

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the player:
```bash
python main.py
```

Or open a file directly:
```bash
python main.py /path/to/video.mp4
```

### Controls

- **Open**: Click the 📂 Open button to select a video file
- **Play/Pause**: Click the ▶️ Play / ⏸️ Pause button
- **Seek**: Drag the timeline slider to jump to any position
- **Volume**: Adjust individual track volumes with the sliders in the Audio Tracks panel
- **Mute**: Click the 🔊/🔇 button to mute individual tracks

## Supported Formats

Any format supported by FFmpeg, including:
- MP4 (H.264, H.265)
- MKV
- AVI
- MOV
- WebM
- And many more...

## Architecture

```
main.py              - Application entry point and main controller
src/
  video_decoder.py   - Video decoding thread using PyAV
  audio_decoder.py   - Audio decoding and playback using sounddevice
  sync.py            - Audio/video synchronization controller
  gui.py             - PyQt6 GUI components
```

## Technology Stack

- **[PyAV](https://pyav.org/)**: Python bindings for FFmpeg, used for video/audio decoding
- **[PyQt6](https://doc.qt.io/qtforpython-6/)**: Cross-platform GUI framework
- **[sounddevice](https://python-sounddevice.readthedocs.io/)**: Low-latency audio I/O
- **[NumPy](https://numpy.org/)**: Efficient array operations for frame handling

## License

MIT License
