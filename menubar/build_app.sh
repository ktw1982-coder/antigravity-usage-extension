#!/bin/zsh

# Paths definition
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$SCRIPT_DIR"
APP_DIR="$BASE_DIR/AntigravityMonitor.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "Creating macOS application bundle directory structure..."
mkdir -p "$MACOS_DIR"
mkdir -p "$RESOURCES_DIR"

# Cleanup old binary/script/icon if exists
if [ -f "$MACOS_DIR/AntigravityMonitor" ]; then
    rm -f "$MACOS_DIR/AntigravityMonitor"
fi
if [ -f "$RESOURCES_DIR/server.py" ]; then
    rm -f "$RESOURCES_DIR/server.py"
fi
if [ -f "$RESOURCES_DIR/AppIcon.icns" ]; then
    rm -f "$RESOURCES_DIR/AppIcon.icns"
fi

echo "Compiling Swift source code..."
swiftc -sdk $(xcrun --show-sdk-path) -framework AppKit -framework UserNotifications "$BASE_DIR/app.swift" -o "$MACOS_DIR/AntigravityMonitor"

if [ $? -ne 0 ]; then
    echo "❌ Swift compilation failed!"
    exit 1
fi

echo "Copying Info.plist configuration..."
cp "$BASE_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"

echo "Copying Python backend script into Resources (Enabling Standalone App Mode)..."
cp "$BASE_DIR/../backend/server.py" "$RESOURCES_DIR/server.py"

echo "Copying AppIcon.icns into Resources..."
if [ -f "$BASE_DIR/AppIcon.icns" ]; then
    cp "$BASE_DIR/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
else
    echo "⚠️ Warning: AppIcon.icns not found at $BASE_DIR/AppIcon.icns"
fi

echo "Setting executable permissions..."
chmod +x "$MACOS_DIR/AntigravityMonitor"
chmod +x "$RESOURCES_DIR/server.py"

echo "✅ Standalone App bundle packaging complete: $APP_DIR"
echo "You can now safely move $APP_DIR to /Applications or any folder. It contains everything inside!"
