# GlobalPlatform GUI - Cross-platform build system
# Usage:
#   make linux      - Build Linux AppImage
#   make windows    - Build Windows executable (on Windows)
#   make macos      - Build macOS .app bundle (on macOS)
#   make all        - Build for current platform
#   make clean      - Clean build artifacts
#   make test       - Run tests
#   make dev        - Install development dependencies

SHELL := /bin/bash
.PHONY: all linux windows macos clean test dev help

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
	@echo "Targets:"
	@echo "  make linux     - Build Linux AppImage"
	@echo "  make windows   - Build Windows executable"
	@echo "  make macos     - Build macOS .app bundle"
	@echo "  make all       - Build for current platform ($(PLATFORM))"
	@echo "  make clean     - Clean build artifacts"
	@echo "  make test      - Run tests"
	@echo "  make dev       - Install development dependencies"
	@echo ""
	@echo "Current platform: $(PLATFORM)"

# Linux AppImage build
linux:
	@echo "Building Linux AppImage..."
	chmod +x build_scripts/linux/build_appimage.sh
	./build_scripts/linux/build_appimage.sh

# macOS .app bundle build
macos:
	@echo "Building macOS .app bundle..."
	chmod +x build_scripts/macos/build_macos.sh build_scripts/macos/create_icns.sh
	./build_scripts/macos/build_macos.sh

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
