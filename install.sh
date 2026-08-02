#!/usr/bin/env bash

set -e

echo "======================================================"
echo "    Antigravity Quota Monitor Installer for macOS"
echo "======================================================"

REPO="ktw1982-coder/antigravity-usage-extension"
LATEST_RELEASE_URL="https://github.com/${REPO}/releases/download/v1.5.2/AntigravityMonitor-v1.5.2-macOS.zip"
TMP_DIR=$(mktemp -d)
ZIP_FILE="${TMP_DIR}/AntigravityMonitor.zip"

echo "[*] Downloading latest release from GitHub..."
curl -fsSL -o "${ZIP_FILE}" "${LATEST_RELEASE_URL}"

echo "[*] Unpacking application..."
unzip -q "${ZIP_FILE}" -d "${TMP_DIR}"

echo "[*] Installing to /Applications..."
if [ -d "/Applications/AntigravityMonitor.app" ]; then
    echo "[!] Removing existing installation in /Applications..."
    rm -rf "/Applications/AntigravityMonitor.app"
fi

mv "${TMP_DIR}/AntigravityMonitor.app" "/Applications/"

echo "[*] Cleaning up temporary files..."
rm -rf "${TMP_DIR}"

echo "======================================================"
echo "✅ Antigravity Monitor installed successfully to /Applications!"
echo "🚀 Launching app now..."
echo "======================================================"

open "/Applications/AntigravityMonitor.app"
