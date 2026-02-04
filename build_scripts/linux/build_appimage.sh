#!/bin/bash
# Build Linux AppImage for GlobalPlatform GUI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/dist"
APPDIR="$BUILD_DIR/GlobalPlatformGUI.AppDir"

echo "=== Building GlobalPlatform GUI AppImage ==="
echo "Project root: $PROJECT_ROOT"

# Ensure we're in project root
cd "$PROJECT_ROOT"

# Check for required tools
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: pyinstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Download appimagetool if not present
APPIMAGETOOL="$SCRIPT_DIR/appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -O "$APPIMAGETOOL" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Clean previous builds and Python cache
echo "Cleaning previous builds..."
rm -rf "$BUILD_DIR/gp_gui" "$APPDIR" "$BUILD_DIR"/*.AppImage
echo "Clearing Python cache..."
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_ROOT" -name "*.pyc" -delete 2>/dev/null || true

# Run PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean --noconfirm linux.spec

# Create AppDir structure
echo "Creating AppDir structure..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller output to AppDir
cp -r "$BUILD_DIR/gp_gui/"* "$APPDIR/usr/bin/"

# Copy desktop file
cp "$SCRIPT_DIR/gp_gui.desktop" "$APPDIR/"
cp "$SCRIPT_DIR/gp_gui.desktop" "$APPDIR/usr/share/applications/"

# Convert and copy icon (use ImageMagick if available, otherwise use favicon.ico directly)
if command -v convert &> /dev/null; then
    echo "Converting icon with ImageMagick..."
    convert "$PROJECT_ROOT/favicon.ico" -resize 256x256 "$APPDIR/gp_gui.png"
else
    echo "Warning: ImageMagick not found. Using favicon.ico as fallback."
    cp "$PROJECT_ROOT/favicon.ico" "$APPDIR/gp_gui.png"
fi
cp "$APPDIR/gp_gui.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"

# Create AppRun script
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/gp_gui" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Build AppImage
echo "Building AppImage..."
APPIMAGE_PATH="$BUILD_DIR/GlobalPlatformGUI-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$APPIMAGE_PATH"

# GPG Signing (optional - requires GPG key)
SIGN_GPG="${SIGN_GPG:-false}"
GPG_KEY="${GPG_KEY:-}"

if [ "$SIGN_GPG" = "true" ]; then
    echo ""
    echo "=== GPG Signing ==="
    if command -v gpg &> /dev/null; then
        GPG_ARGS="--detach-sign --armor"
        if [ -n "$GPG_KEY" ]; then
            GPG_ARGS="$GPG_ARGS --default-key $GPG_KEY"
        fi

        echo "Creating GPG signature..."
        gpg $GPG_ARGS "$APPIMAGE_PATH"

        if [ -f "${APPIMAGE_PATH}.asc" ]; then
            echo "GPG signature created: ${APPIMAGE_PATH}.asc"
        else
            echo "Warning: GPG signing may have failed"
        fi
    else
        echo "Warning: gpg not found, skipping GPG signing"
    fi
fi

# Generate checksums
echo ""
echo "=== Generating Checksums ==="
cd "$BUILD_DIR"
sha256sum "$(basename "$APPIMAGE_PATH")" > "$(basename "$APPIMAGE_PATH").sha256"
echo "SHA256: $(cat "$(basename "$APPIMAGE_PATH").sha256")"

echo ""
echo "=== Build Complete ==="
echo "AppImage: $APPIMAGE_PATH"
echo "Checksum: ${APPIMAGE_PATH}.sha256"
if [ -f "${APPIMAGE_PATH}.asc" ]; then
    echo "GPG Sig:  ${APPIMAGE_PATH}.asc"
fi
echo ""
echo "To test: $APPIMAGE_PATH"
echo ""
echo "To build with GPG signing:"
echo "  SIGN_GPG=true GPG_KEY=your-key-id ./build_appimage.sh"
