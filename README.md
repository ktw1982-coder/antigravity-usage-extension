# Antigravity Quota Monitor

[![macOS](https://img.shields.io/badge/OS-macOS-lightgrey.svg?style=flat&logo=apple)](https://www.apple.com/macos/)
[![Swift](https://img.shields.io/badge/Swift-5.0+-orange.svg?style=flat&logo=swift)](https://swift.org)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat&logo=python)](https://www.python.org)
[![Release](https://img.shields.io/badge/Release-v1.5.5-brightgreen.svg)](https://github.com/ktw1982-coder/antigravity-usage-extension/releases/tag/v1.5.5)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight native macOS Menu Bar application, Web Analytics Dashboard, and Chrome Extension designed to monitor real-time quota usage for **Google Antigravity (AGY)** models (Gemini, Claude, and GPT).

---

## 🍺 Install via Homebrew Cask (Recommended)

Install **Antigravity Monitor** directly via Homebrew Cask with a single command:

```bash
brew install --cask ktw1982-coder/tap/antigravity-monitor
```

---

## ⚡ Alternative Quick Install (Script)

Alternatively, install using the quick setup script:

```bash
curl -fsSL https://raw.githubusercontent.com/ktw1982-coder/antigravity-usage-extension/main/install.sh | bash
```

---

## 💡 Why Antigravity Monitor?

Unlike IDE-bound extensions or resource-heavy Electron apps, **Antigravity Monitor** offers:

- 📊 **Web Analytics Dashboard**: Includes a sleek, dark-mode web dashboard (`http://localhost:8484/dashboard`) with 24-hour interactive usage trend charts.
- 🚀 **IDE Independent**: Works globally across your Mac whether you use Xcode, Cursor, PyCharm, or terminal. No need to keep VS Code open.
- 🪶 **Ultra-Lightweight (~15MB RAM)**: Built with pure native Swift and AppKit. Zero heavy Electron bloat.
- 🔔 **Proactive Push Alerts**: Get native macOS notifications at 80% and 90% quota thresholds before running out of quota mid-task.
- 🌐 **Dual Ecosystem**: Use both the native macOS Status Bar app, Web Dashboard, and Chrome Extension (Manifest V3).

---

## 🌟 Features

- 📊 **Real-time Quota Tracking**: Displays weekly and 5-hour quota percentages and refresh reset times for Gemini, Claude, and GPT models.
- 📈 **24-Hour Usage Trend Charts**: Visualize historical quota consumption curves over time powered by Chart.js.
- 🍏 **Native macOS Menu Bar App**: Built with Swift for a lightweight, seamless experience on your menu bar.
- ⚙️ **Preferences Window (Cmd + ,)**: Toggle push notifications and customize preferences.
- 🔔 **Push Notifications**: Receive instant macOS notifications when quota usage reaches 80% or 90%.
- 🚀 **Launch at Login**: Easily toggle auto-start on system boot directly from the menu bar dropdown.
- 🛡️ **Robust Parsing Engine**: Built-in fallback parsing pattern to ensure stability across CLI updates and account tiers (Free, Pro, Ultra, Enterprise).
- 🌐 **Chrome Extension**: Quick popup interface (Manifest V3) with one-click dashboard access inside Google Chrome.

---

## 🏗️ Architecture

```text
┌───────────────────────────┐      ┌───────────────────────────┐
│     macOS MenuBar App     │      │     Chrome Extension      │
│         (Swift)           │      │       (Manifest V3)       │
└─────────────┬─────────────┘      └─────────────┬─────────────┘
              │                                  │
              ├──────────────────────────────────┘
              │ HTTP GET /usage & /dashboard
              ▼
┌──────────────────────────────────────────────┐
│          Local Python Backend                │
│    (server.py + Web Analytics Dashboard)     │
└──────────────────────┬───────────────────────┘
                       │ PTY / Interactive CLI
                       ▼
┌──────────────────────────────────────────────┐
│          Antigravity CLI (agy)               │
└──────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

Before installing, ensure you have the following installed on your environment:

1. **macOS**: 10.13 High Sierra or newer.
2. **Google Antigravity CLI (`agy`)**: Make sure `agy` is installed and accessible in your environment (default path: `~/.local/bin/agy` or available in `$PATH`).
3. **Python 3**: Required to run the local backend server.

---

## 🛠️ Manual Build & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ktw1982-coder/antigravity-usage-extension.git
cd antigravity-usage-extension
```

### 2. macOS Menu Bar App Build

```bash
cd menubar
zsh build_app.sh
```

#### Move to Applications Folder:
```bash
cp -R AntigravityMonitor.app /Applications/
```

### 3. Chrome Extension Setup (Optional)

1. Open **Google Chrome** and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top-right corner).
3. Click **Load unpacked**.
4. Select the `extension/` directory from this repository.

---

## 💡 Usage

### Using the macOS Menu Bar App & Web Dashboard
1. Once launched, you will see an icon in your status bar displaying current quota percentage (e.g., `AG: 85%`).
2. Click the icon to view:
   - **Gemini & Claude Models Quota**: Weekly and 5-Hour usage limits along with reset countdowns.
   - **Open Dashboard 📊 (Cmd + D)**: Opens the interactive Web Analytics Dashboard in your browser.
   - **Preferences... (Cmd + ,)**: Toggle push notifications and customize settings.
   - **Launch at Login**: Toggle auto-start on macOS startup.
   - **Force Refresh**: Instantly query and update quota data.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
