#!/bin/bash
# Build macOS .app bundle for GlobalPlatform GUI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/dist"

echo "=== Building GlobalPlatform GUI for macOS ==="
echo "Project root: $PROJECT_ROOT"

# Ensure we're in project root
cd "$PROJECT_ROOT"

# Check for required tools
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: pyinstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Create .icns icon if it doesn't exist
ICNS_FILE="$SCRIPT_DIR/gp_gui.icns"
if [ ! -f "$ICNS_FILE" ]; then
    echo "Creating macOS icon..."
    "$SCRIPT_DIR/create_icns.sh"
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf "$BUILD_DIR/gp_gui" "$BUILD_DIR/GlobalPlatform GUI.app"

# Run PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean --noconfirm macos.spec

echo ""
echo "=== Build Complete ==="
echo "App bundle: $BUILD_DIR/GlobalPlatform GUI.app"
echo ""
echo "To test: open '$BUILD_DIR/GlobalPlatform GUI.app'"
echo ""
echo "To create DMG installer, run:"
echo "  hdiutil create -volname 'GlobalPlatform GUI' -srcfolder '$BUILD_DIR/GlobalPlatform GUI.app' -ov -format UDZO '$BUILD_DIR/GlobalPlatformGUI.dmg'"
