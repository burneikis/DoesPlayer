#!/usr/bin/env python3
"""
DoesPlayer Build Script

Cross-platform build script for creating distributable packages:
- macOS: .app bundle and .dmg installer
- Windows: .exe and NSIS installer

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build artifacts
"""

import os
import sys
import shutil
import subprocess
import platform
import argparse
from pathlib import Path

# Build configuration
APP_NAME = "DoesPlayer"
APP_VERSION = "1.0.0"
APP_AUTHOR = "DoesPlayer Team"
APP_DESCRIPTION = "A high-performance video player with multitrack audio support"
MAIN_SCRIPT = "main.py"
ICON_MACOS = "assets/icon.icns"
ICON_WINDOWS = "assets/icon.ico"

# Directories
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")
ASSETS_DIR = Path("assets")


def clean_build():
    """Remove all build artifacts."""
    print("🧹 Cleaning build artifacts...")
    
    dirs_to_clean = [BUILD_DIR, DIST_DIR, Path("__pycache__"), Path(".eggs")]
    files_to_clean = list(Path(".").glob("*.spec"))
    
    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"   Removed {d}/")
    
    for f in files_to_clean:
        f.unlink()
        print(f"   Removed {f}")
    
    # Clean __pycache__ in subdirectories
    for pycache in Path(".").rglob("__pycache__"):
        shutil.rmtree(pycache)
        print(f"   Removed {pycache}/")
    
    print("✅ Clean complete!")


def ensure_assets():
    """Ensure assets directory and placeholder icons exist."""
    ASSETS_DIR.mkdir(exist_ok=True)
    
    # Check for icons, create placeholders if needed
    icns_path = Path(ICON_MACOS)
    ico_path = Path(ICON_WINDOWS)
    
    if not icns_path.exists():
        print(f"⚠️  Warning: {ICON_MACOS} not found. Build will use default icon.")
    
    if not ico_path.exists():
        print(f"⚠️  Warning: {ICON_WINDOWS} not found. Build will use default icon.")


def check_dependencies():
    """Check that required build dependencies are installed."""
    print("🔍 Checking build dependencies...")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"   ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("   ✗ PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    system = platform.system()
    
    if system == "Darwin":
        # Check for create-dmg on macOS
        result = subprocess.run(["which", "create-dmg"], capture_output=True)
        if result.returncode != 0:
            print("   ⚠️  create-dmg not found. Install with: brew install create-dmg")
            print("      DMG creation will be skipped without it.")
    
    elif system == "Windows":
        # Check for NSIS on Windows
        nsis_paths = [
            Path(os.environ.get("PROGRAMFILES", "")) / "NSIS" / "makensis.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "NSIS" / "makensis.exe",
            Path("C:/Program Files/NSIS/makensis.exe"),
            Path("C:/Program Files (x86)/NSIS/makensis.exe"),
        ]
        nsis_found = any(p.exists() for p in nsis_paths)
        if not nsis_found:
            # Try to find in PATH
            result = subprocess.run(["where", "makensis"], capture_output=True, shell=True)
            nsis_found = result.returncode == 0
        
        if not nsis_found:
            print("   ⚠️  NSIS not found. Install from: https://nsis.sourceforge.io/")
            print("      Installer creation will be skipped without it.")


def get_pyinstaller_args():
    """Get PyInstaller arguments based on platform."""
    system = platform.system()
    
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",  # No console window
        "--add-data", f"window_config.json{os.pathsep}.",
    ]
    
    # Add source files
    args.extend(["--add-data", f"src{os.pathsep}src"])
    
    # Platform-specific options
    if system == "Darwin":
        args.extend([
            "--osx-bundle-identifier", f"com.doesplayer.{APP_NAME.lower()}",
        ])
        if Path(ICON_MACOS).exists():
            args.extend(["--icon", ICON_MACOS])
    
    elif system == "Windows":
        if Path(ICON_WINDOWS).exists():
            args.extend(["--icon", ICON_WINDOWS])
    
    # Hidden imports for PyQt6 and av
    hidden_imports = [
        "PyQt6.QtCore",
        "PyQt6.QtGui", 
        "PyQt6.QtWidgets",
        "av",
        "sounddevice",
        "numpy",
    ]
    for imp in hidden_imports:
        args.extend(["--hidden-import", imp])
    
    args.append(MAIN_SCRIPT)
    
    return args


def build_macos():
    """Build macOS .app bundle and .dmg installer."""
    print("🍎 Building for macOS...")
    
    # Build with PyInstaller
    args = get_pyinstaller_args()
    print(f"   Running PyInstaller...")
    subprocess.check_call(args)
    
    app_path = DIST_DIR / f"{APP_NAME}.app"
    
    if not app_path.exists():
        print("❌ Error: .app bundle not created!")
        return False
    
    print(f"   ✅ Created {app_path}")
    
    # Create DMG
    dmg_path = DIST_DIR / f"{APP_NAME}-{APP_VERSION}.dmg"
    
    # Check if create-dmg is available
    result = subprocess.run(["which", "create-dmg"], capture_output=True)
    if result.returncode == 0:
        print("   Creating DMG installer...")
        
        # Remove existing DMG if present
        if dmg_path.exists():
            dmg_path.unlink()
        
        dmg_args = [
            "create-dmg",
            "--volname", APP_NAME,
            "--window-pos", "200", "120",
            "--window-size", "600", "400",
            "--icon-size", "100",
            "--icon", f"{APP_NAME}.app", "150", "190",
            "--app-drop-link", "450", "190",
            "--hide-extension", f"{APP_NAME}.app",
            str(dmg_path),
            str(app_path),
        ]
        
        # Add background image if exists
        bg_path = ASSETS_DIR / "dmg_background.png"
        if bg_path.exists():
            dmg_args.insert(-2, "--background")
            dmg_args.insert(-2, str(bg_path))
        
        try:
            subprocess.check_call(dmg_args)
            print(f"   ✅ Created {dmg_path}")
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  DMG creation failed: {e}")
            print("      You can still use the .app bundle directly.")
    else:
        print("   ⚠️  Skipping DMG creation (create-dmg not installed)")
        print("      Install with: brew install create-dmg")
    
    return True


def build_windows():
    """Build Windows .exe and NSIS installer."""
    print("🪟 Building for Windows...")
    
    # Build with PyInstaller
    args = get_pyinstaller_args()
    print(f"   Running PyInstaller...")
    subprocess.check_call(args)
    
    exe_dir = DIST_DIR / APP_NAME
    exe_path = exe_dir / f"{APP_NAME}.exe"
    
    if not exe_path.exists():
        print("❌ Error: .exe not created!")
        return False
    
    print(f"   ✅ Created {exe_path}")
    
    # Find NSIS
    nsis_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "NSIS" / "makensis.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "NSIS" / "makensis.exe",
        Path("C:/Program Files/NSIS/makensis.exe"),
        Path("C:/Program Files (x86)/NSIS/makensis.exe"),
    ]
    
    makensis = None
    for p in nsis_paths:
        if p.exists():
            makensis = p
            break
    
    if makensis is None:
        # Try PATH
        result = subprocess.run(["where", "makensis"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            makensis = Path(result.stdout.strip().split("\n")[0])
    
    nsi_script = Path("installer.nsi")
    
    if makensis and nsi_script.exists():
        print("   Creating NSIS installer...")
        
        try:
            subprocess.check_call([
                str(makensis),
                f"/DVERSION={APP_VERSION}",
                f"/DAPP_NAME={APP_NAME}",
                str(nsi_script)
            ])
            installer_path = DIST_DIR / f"{APP_NAME}-{APP_VERSION}-Setup.exe"
            print(f"   ✅ Created {installer_path}")
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  NSIS installer creation failed: {e}")
    else:
        if not makensis:
            print("   ⚠️  Skipping installer creation (NSIS not installed)")
            print("      Install from: https://nsis.sourceforge.io/")
        if not nsi_script.exists():
            print("   ⚠️  installer.nsi not found")
    
    return True


def build_linux():
    """Build Linux executable."""
    print("🐧 Building for Linux...")
    
    # Build with PyInstaller
    args = get_pyinstaller_args()
    # Linux doesn't need --windowed, but we keep it for consistency
    print(f"   Running PyInstaller...")
    subprocess.check_call(args)
    
    exe_path = DIST_DIR / APP_NAME / APP_NAME
    
    if not exe_path.exists():
        print("❌ Error: Executable not created!")
        return False
    
    print(f"   ✅ Created {exe_path}")
    
    # Create tar.gz archive
    archive_name = f"{APP_NAME}-{APP_VERSION}-linux"
    archive_path = DIST_DIR / f"{archive_name}.tar.gz"
    
    print("   Creating tar.gz archive...")
    import tarfile
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(DIST_DIR / APP_NAME, arcname=APP_NAME)
    
    print(f"   ✅ Created {archive_path}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Build DoesPlayer for distribution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build artifacts only
        """
    )
    parser.add_argument(
        "--clean", 
        action="store_true",
        help="Clean build artifacts and exit"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}"
    )
    
    args = parser.parse_args()
    
    if args.clean:
        clean_build()
        return 0
    
    print(f"{'='*50}")
    print(f"  {APP_NAME} Build Script v{APP_VERSION}")
    print(f"{'='*50}\n")
    
    system = platform.system()
    print(f"📦 Target platform: {system}")
    print()
    
    # Pre-build checks
    ensure_assets()
    check_dependencies()
    print()
    
    # Clean previous build
    clean_build()
    print()
    
    # Build for current platform
    success = False
    
    if system == "Darwin":
        success = build_macos()
    elif system == "Windows":
        success = build_windows()
    elif system == "Linux":
        success = build_linux()
    else:
        print(f"❌ Unsupported platform: {system}")
        return 1
    
    print()
    if success:
        print(f"{'='*50}")
        print(f"  ✅ Build complete!")
        print(f"  📁 Output: {DIST_DIR.absolute()}/")
        print(f"{'='*50}")
        return 0
    else:
        print(f"{'='*50}")
        print(f"  ❌ Build failed!")
        print(f"{'='*50}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
