# GlobalPlatform GUI - Cross-platform build system
# Usage:
#   make linux          - Build Linux AppImage
#   make linux-signed   - Build Linux AppImage with GPG signature
#   make windows        - Build Windows executable (on Windows)
#   make macos          - Build macOS .app bundle (on macOS)
#   make macos-signed   - Build macOS with GPG signature
#   make all            - Build for current platform
#   make clean          - Clean build artifacts
#   make test           - Run tests
#   make dev            - Install development dependencies
#
# Signing options (set via environment):
#   GPG_KEY           - GPG key ID for signing (e.g., GPG_KEY=4F08C3EF8040B5C7)
#   CODESIGN_IDENTITY - macOS Developer ID (e.g., "Developer ID Application: Name (TEAMID)")
#   SIGNTOOL_CERT     - Windows certificate path
#   SIGNTOOL_PASSWORD - Windows certificate password

SHELL := /bin/bash
.PHONY: all linux linux-signed windows macos macos-signed clean test dev help sign-verify

# Detect OS
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    PLATFORM := linux
endif
ifeq ($(UNAME_S),Darwin)
    PLATFORM := macos
endif
ifeq ($(OS),Windows_NT)
    PLATFORM := windows
endif

# Default target
all: $(PLATFORM)

help:
	@echo "GlobalPlatform GUI Build System"
	@echo ""
	@echo "Build Targets:"
	@echo "  make linux        - Build Linux AppImage"
	@echo "  make linux-signed - Build Linux AppImage with GPG signature"
	@echo "  make windows      - Build Windows executable"
	@echo "  make macos        - Build macOS .app bundle + DMG"
	@echo "  make macos-signed - Build macOS with GPG signature"
	@echo "  make all          - Build for current platform ($(PLATFORM))"
	@echo ""
	@echo "Other Targets:"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make test         - Run tests"
	@echo "  make dev          - Install development dependencies"
	@echo "  make sign-verify  - Verify GPG signatures in dist/"
	@echo ""
	@echo "Signing Options (environment variables):"
	@echo "  GPG_KEY=<key-id>              - GPG key for signing"
	@echo "  CODESIGN_IDENTITY=<identity>  - macOS Developer ID"
	@echo "  SIGNTOOL_CERT=<path>          - Windows certificate file"
	@echo ""
	@echo "Current platform: $(PLATFORM)"

# Linux AppImage build
linux:
	@echo "Building Linux AppImage..."
	chmod +x build_scripts/linux/build_appimage.sh
	./build_scripts/linux/build_appimage.sh

# Linux AppImage build with GPG signing
linux-signed:
	@echo "Building Linux AppImage with GPG signature..."
	chmod +x build_scripts/linux/build_appimage.sh
	SIGN_GPG=true GPG_KEY=$(GPG_KEY) ./build_scripts/linux/build_appimage.sh

# macOS .app bundle build
macos:
	@echo "Building macOS .app bundle..."
	chmod +x build_scripts/macos/build_macos.sh build_scripts/macos/create_icns.sh
	./build_scripts/macos/build_macos.sh

# macOS build with GPG signing (and optional Apple code signing)
macos-signed:
	@echo "Building macOS .app bundle with signing..."
	chmod +x build_scripts/macos/build_macos.sh build_scripts/macos/create_icns.sh
	SIGN_GPG=true GPG_KEY=$(GPG_KEY) CODESIGN_IDENTITY="$(CODESIGN_IDENTITY)" ./build_scripts/macos/build_macos.sh

# Windows executable build
windows:
ifeq ($(OS),Windows_NT)
	@echo "Building Windows executable..."
	build_scripts\windows\build_windows.bat
else
	@echo "Windows builds must be run on Windows."
	@echo "Use: build_scripts/windows/build_windows.bat"
endif

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ __pycache__/
	rm -rf *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@echo "Clean complete."

# Run tests
test:
	@echo "Running tests..."
	python -m pytest tests/ -v

# Install development dependencies
dev:
	@echo "Installing development dependencies..."
	pip install -r requirements.txt
	pip install pyinstaller pytest black

# Quick PyInstaller build (current platform, one-file)
quick:
ifeq ($(PLATFORM),linux)
	pyinstaller --clean --noconfirm linux.spec
else ifeq ($(PLATFORM),macos)
	pyinstaller --clean --noconfirm macos.spec
else ifeq ($(PLATFORM),windows)
	pyinstaller --clean --noconfirm windows.spec
endif

# Format code
format:
	black .

# Check code style
lint:
	black --check .

# Verify GPG signatures
sign-verify:
	@echo "Verifying GPG signatures in dist/..."
	@for sig in dist/*.asc; do \
		if [ -f "$$sig" ]; then \
			echo "Verifying: $$sig"; \
			gpg --verify "$$sig" && echo "  ✓ Valid" || echo "  ✗ Invalid"; \
		fi \
	done
	@echo ""
	@echo "Verifying checksums..."
	@for sum in dist/*.sha256; do \
		if [ -f "$$sum" ]; then \
			echo "Checking: $$sum"; \
			cd dist && sha256sum -c "$$(basename $$sum)" && echo "  ✓ Valid" || echo "  ✗ Invalid"; \
			cd ..; \
		fi \
	done
