# DoesPlayer

Video player that supports multi track audio simultaneously, and has some support for framewise navigation.

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

## Keybinds

- `Space`: Play/Pause
- `Left Arrow`: Seek backward 1 frame
- `Right Arrow`: Seek forward 1 frame
- `Up Arrow`: Increase volume
- `Down Arrow`: Decrease volume
- `[`: Seek backward 5 seconds
- `]`: Seek forward 10 seconds
- `{`: Seek backward 15 seconds
- `A`: Toggle audio mixer
