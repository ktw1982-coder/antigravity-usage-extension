#!/bin/zsh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$SCRIPT_DIR"
SRC_IMG="${1:-$BASE_DIR/icon.png}"
ICONSET_DIR="$BASE_DIR/AppIcon.iconset"

echo "Creating iconset directory..."
mkdir -p "$ICONSET_DIR"

# Resize images and convert format explicitly to PNG using sips
echo "Resizing and converting icons to PNG..."
sips -s format png -z 16 16     "$SRC_IMG" --out "$ICONSET_DIR/icon_16x16.png"
sips -s format png -z 32 32     "$SRC_IMG" --out "$ICONSET_DIR/icon_16x16@2x.png"
sips -s format png -z 32 32     "$SRC_IMG" --out "$ICONSET_DIR/icon_32x32.png"
sips -s format png -z 64 64     "$SRC_IMG" --out "$ICONSET_DIR/icon_32x32@2x.png"
sips -s format png -z 128 128   "$SRC_IMG" --out "$ICONSET_DIR/icon_128x128.png"
sips -s format png -z 256 256   "$SRC_IMG" --out "$ICONSET_DIR/icon_128x128@2x.png"
sips -s format png -z 256 256   "$SRC_IMG" --out "$ICONSET_DIR/icon_256x256.png"
sips -s format png -z 512 512   "$SRC_IMG" --out "$ICONSET_DIR/icon_256x256@2x.png"
sips -s format png -z 512 512   "$SRC_IMG" --out "$ICONSET_DIR/icon_512x512.png"
sips -s format png -z 1024 1024 "$SRC_IMG" --out "$ICONSET_DIR/icon_512x512@2x.png"

# Convert to icns
echo "Generating AppIcon.icns..."
iconutil -c icns "$ICONSET_DIR" --o "$BASE_DIR/AppIcon.icns"

# Clean up
echo "Cleaning up temporary iconset..."
rm -rf "$ICONSET_DIR"

echo "Done! AppIcon.icns generated at $BASE_DIR/AppIcon.icns"
