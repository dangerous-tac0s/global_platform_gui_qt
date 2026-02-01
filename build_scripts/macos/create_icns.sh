#!/bin/bash
# Convert favicon.ico to macOS .icns format
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ICONSET_DIR="$SCRIPT_DIR/gp_gui.iconset"
ICO_FILE="$PROJECT_ROOT/favicon.ico"
ICNS_FILE="$SCRIPT_DIR/gp_gui.icns"

echo "Creating macOS .icns icon from favicon.ico..."

# Check for sips (macOS) or ImageMagick
if command -v sips &> /dev/null; then
    # macOS native approach
    echo "Using sips (macOS native)..."

    # Create iconset directory
    mkdir -p "$ICONSET_DIR"

    # First convert ICO to PNG (largest size)
    if command -v convert &> /dev/null; then
        convert "$ICO_FILE" -resize 1024x1024 "$SCRIPT_DIR/icon_1024.png"
    else
        # Try using sips directly (may not work with ICO)
        echo "Warning: ImageMagick not found. Attempting sips conversion..."
        sips -s format png "$ICO_FILE" --out "$SCRIPT_DIR/icon_1024.png" 2>/dev/null || {
            echo "Error: Cannot convert ICO file. Install ImageMagick: brew install imagemagick"
            exit 1
        }
    fi

    # Generate all required sizes
    sips -z 16 16     "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_16x16.png"
    sips -z 32 32     "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_16x16@2x.png"
    sips -z 32 32     "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_32x32.png"
    sips -z 64 64     "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_32x32@2x.png"
    sips -z 128 128   "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_128x128.png"
    sips -z 256 256   "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_128x128@2x.png"
    sips -z 256 256   "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_256x256.png"
    sips -z 512 512   "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_256x256@2x.png"
    sips -z 512 512   "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_512x512.png"
    sips -z 1024 1024 "$SCRIPT_DIR/icon_1024.png" --out "$ICONSET_DIR/icon_512x512@2x.png"

    # Create .icns file
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"

    # Cleanup
    rm -rf "$ICONSET_DIR" "$SCRIPT_DIR/icon_1024.png"

elif command -v convert &> /dev/null; then
    # Linux/cross-platform approach using ImageMagick
    echo "Using ImageMagick..."

    # Create iconset directory
    mkdir -p "$ICONSET_DIR"

    # Generate all required sizes
    convert "$ICO_FILE" -resize 16x16     "$ICONSET_DIR/icon_16x16.png"
    convert "$ICO_FILE" -resize 32x32     "$ICONSET_DIR/icon_16x16@2x.png"
    convert "$ICO_FILE" -resize 32x32     "$ICONSET_DIR/icon_32x32.png"
    convert "$ICO_FILE" -resize 64x64     "$ICONSET_DIR/icon_32x32@2x.png"
    convert "$ICO_FILE" -resize 128x128   "$ICONSET_DIR/icon_128x128.png"
    convert "$ICO_FILE" -resize 256x256   "$ICONSET_DIR/icon_128x128@2x.png"
    convert "$ICO_FILE" -resize 256x256   "$ICONSET_DIR/icon_256x256.png"
    convert "$ICO_FILE" -resize 512x512   "$ICONSET_DIR/icon_256x256@2x.png"
    convert "$ICO_FILE" -resize 512x512   "$ICONSET_DIR/icon_512x512.png"
    convert "$ICO_FILE" -resize 1024x1024 "$ICONSET_DIR/icon_512x512@2x.png"

    # Check for png2icns (from libicns)
    if command -v png2icns &> /dev/null; then
        png2icns "$ICNS_FILE" "$ICONSET_DIR"/*.png
    else
        echo "Warning: png2icns not found. Iconset created but .icns conversion requires macOS."
        echo "Copy $ICONSET_DIR to a Mac and run: iconutil -c icns gp_gui.iconset -o gp_gui.icns"
        exit 0
    fi

    # Cleanup
    rm -rf "$ICONSET_DIR"
else
    echo "Error: Neither sips nor ImageMagick found."
    echo "On macOS: Tools should be built-in, or install: brew install imagemagick"
    echo "On Linux: sudo apt install imagemagick"
    exit 1
fi

echo "Created: $ICNS_FILE"
