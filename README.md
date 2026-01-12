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

## Building Distributables

DoesPlayer can be packaged into standalone executables and installers for distribution.

### Prerequisites

Install PyInstaller (required for all platforms):
```bash
pip install pyinstaller
```

### macOS

**Additional requirements:**
- [create-dmg](https://github.com/create-dmg/create-dmg) for DMG creation:
  ```bash
  brew install create-dmg
  ```

**Build:**
```bash
python build.py
```

**Output:**
- `dist/DoesPlayer.app` - Standalone application bundle
- `dist/DoesPlayer-1.0.0.dmg` - DMG installer with drag-to-Applications

### Windows

**Additional requirements:**
- [NSIS](https://nsis.sourceforge.io/) (Nullsoft Scriptable Install System)
  - Download and install from https://nsis.sourceforge.io/Download

**Build:**
```bash
python build.py
```

**Output:**
- `dist/DoesPlayer/DoesPlayer.exe` - Standalone executable
- `dist/DoesPlayer-1.0.0-Setup.exe` - NSIS installer

### Linux

**Build:**
```bash
python build.py
```

**Output:**
- `dist/DoesPlayer/DoesPlayer` - Standalone executable
- `dist/DoesPlayer-1.0.0-linux.tar.gz` - Compressed archive

### Build Options

```bash
# Build for current platform
python build.py

# Clean build artifacts
python build.py --clean

# Show version
python build.py --version
```

### Custom Icons

Place your icons in the `assets/` directory:
- `assets/icon.icns` - macOS icon (required for custom icon)
- `assets/icon.ico` - Windows icon (required for custom icon)
- `assets/dmg_background.png` - Optional DMG background image (600x400 recommended)

### Troubleshooting

**macOS:** If you get code signing errors, you may need to sign the app:
```bash
codesign --force --deep --sign - dist/DoesPlayer.app
```

**Windows:** If NSIS is not found, ensure it's installed and either:
- Added to your PATH, or
- Installed in the default location (`C:\Program Files\NSIS` or `C:\Program Files (x86)\NSIS`)
