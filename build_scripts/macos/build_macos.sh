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

APP_BUNDLE="$BUILD_DIR/GlobalPlatform GUI.app"
DMG_PATH="$BUILD_DIR/GlobalPlatformGUI.dmg"

# ============================================
# macOS Code Signing (Optional - requires Apple Developer ID)
# ============================================
# To enable: export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
# To enable notarization: export NOTARIZE_APPLE_ID="your@email.com"
#                         export NOTARIZE_PASSWORD="app-specific-password"
#                         export NOTARIZE_TEAM_ID="TEAMID"

CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
NOTARIZE_APPLE_ID="${NOTARIZE_APPLE_ID:-}"

if [ -n "$CODESIGN_IDENTITY" ]; then
    echo ""
    echo "=== macOS Code Signing ==="
    echo "Signing with: $CODESIGN_IDENTITY"

    # Sign all frameworks and executables inside the app bundle
    find "$APP_BUNDLE" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -exec \
        codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp {} \; 2>/dev/null || true

    # Sign the main app bundle
    codesign --force --deep --sign "$CODESIGN_IDENTITY" --options runtime --timestamp "$APP_BUNDLE"

    # Verify signature
    codesign --verify --verbose "$APP_BUNDLE" && echo "Code signature verified successfully"

    # Notarization (if credentials provided)
    if [ -n "$NOTARIZE_APPLE_ID" ] && [ -n "$NOTARIZE_PASSWORD" ] && [ -n "$NOTARIZE_TEAM_ID" ]; then
        echo ""
        echo "=== Notarization ==="
        # Create ZIP for notarization
        ditto -c -k --keepParent "$APP_BUNDLE" "$BUILD_DIR/app_for_notarization.zip"

        # Submit for notarization
        xcrun notarytool submit "$BUILD_DIR/app_for_notarization.zip" \
            --apple-id "$NOTARIZE_APPLE_ID" \
            --password "$NOTARIZE_PASSWORD" \
            --team-id "$NOTARIZE_TEAM_ID" \
            --wait

        # Staple the notarization ticket
        xcrun stapler staple "$APP_BUNDLE"

        rm "$BUILD_DIR/app_for_notarization.zip"
        echo "Notarization complete"
    fi
else
    echo ""
    echo "Note: Skipping macOS code signing (CODESIGN_IDENTITY not set)"
    echo "To sign, export CODESIGN_IDENTITY=\"Developer ID Application: Your Name (TEAMID)\""
fi

# Create DMG
echo ""
echo "=== Creating DMG ==="
rm -f "$DMG_PATH"
hdiutil create -volname "GlobalPlatform GUI" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"

# Sign DMG if identity provided
if [ -n "$CODESIGN_IDENTITY" ]; then
    codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$DMG_PATH"
fi

# ============================================
# GPG Signing (Optional - works with hardware tokens)
# ============================================
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

        echo "Creating GPG signature for DMG..."
        gpg $GPG_ARGS "$DMG_PATH"

        if [ -f "${DMG_PATH}.asc" ]; then
            echo "GPG signature created: ${DMG_PATH}.asc"
        fi
    else
        echo "Warning: gpg not found, skipping GPG signing"
    fi
fi

# Generate checksums
echo ""
echo "=== Generating Checksums ==="
cd "$BUILD_DIR"
shasum -a 256 "$(basename "$DMG_PATH")" > "$(basename "$DMG_PATH").sha256"
echo "SHA256: $(cat "$(basename "$DMG_PATH").sha256")"

echo ""
echo "=== Build Complete ==="
echo "App bundle: $APP_BUNDLE"
echo "DMG:        $DMG_PATH"
echo "Checksum:   ${DMG_PATH}.sha256"
if [ -f "${DMG_PATH}.asc" ]; then
    echo "GPG Sig:    ${DMG_PATH}.asc"
fi
echo ""
echo "To test: open '$APP_BUNDLE'"
echo ""
echo "Build options:"
echo "  SIGN_GPG=true GPG_KEY=key-id ./build_macos.sh    # GPG sign"
echo "  CODESIGN_IDENTITY=\"...\" ./build_macos.sh        # Apple code sign"
