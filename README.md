# Antigravity Quota Monitor

[![macOS](https://img.shields.io/badge/OS-macOS-lightgrey.svg?style=flat&logo=apple)](https://www.apple.com/macos/)
[![Swift](https://img.shields.io/badge/Swift-5.0+-orange.svg?style=flat&logo=swift)](https://swift.org)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat&logo=python)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight macOS Menu Bar application and Chrome Extension designed to monitor real-time quota usage for **Google Antigravity (AGY)** models (Gemini, Claude, and GPT).

---

## 🌟 Features

- 📊 **Real-time Quota Tracking**: Displays weekly and 5-hour quota percentages and refresh reset times for Gemini, Claude, and GPT models.
- 🍏 **Native macOS Menu Bar App**: Built with Swift for a lightweight, seamless experience on your menu bar.
- 🚀 **Launch at Login**: Easily toggle auto-start on system boot directly from the menu bar dropdown.
- 🌐 **Chrome Extension**: Quick popup interface (Manifest V3) to check quota status directly inside Google Chrome.
- ⚡ **Automated Backend Daemon**: Includes a Python background service (`server.py`) that periodically polls quota data from the `agy` CLI via PTY interaction.

---

## 🏗️ Architecture

```text
┌───────────────────────────┐      ┌───────────────────────────┐
│     macOS MenuBar App     │      │     Chrome Extension      │
│         (Swift)           │      │       (Manifest V3)       │
└─────────────┬─────────────┘      └─────────────┬─────────────┘
              │                                  │
              └───────────────┬──────────────────┘
                              │ HTTP GET /usage
                              ▼
               ┌──────────────────────────────┐
               │    Local Python Backend      │
               │         (server.py)          │
               └──────────────┬───────────────┘
                              │ PTY / Interactive CLI
                              ▼
               ┌──────────────────────────────┐
               │    Antigravity CLI (agy)     │
               └──────────────────────────────┘
```

---

## 📋 Prerequisites

Before installing, ensure you have the following installed on your environment:

1. **macOS**: 10.13 High Sierra or newer.
2. **Google Antigravity CLI (`agy`)**: Make sure `agy` is installed and accessible in your environment (default path: `~/.local/bin/agy` or available in `$PATH`).
3. **Python 3**: Required to run the local backend server.

---

## 🛠️ Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ktw1982-coder/antigravity-usage-extension.git
cd antigravity-usage-extension
```

### 2. macOS Menu Bar App Setup

You can build and package the standalone `.app` bundle using the included build script:

```bash
cd menubar
zsh build_app.sh
```

This generates `AntigravityMonitor.app` inside the `menubar/` directory.

#### Move to Applications Folder (Recommended):
```bash
cp -R AntigravityMonitor.app /Applications/
```

Launch `AntigravityMonitor.app` from `/Applications` or Spotlight.

### 3. Chrome Extension Setup (Optional)

1. Open **Google Chrome** and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the `extension/` directory from this repository.

---

## 💡 Usage

### Using the macOS Menu Bar App
1. Once launched, you will see an icon in your macOS status bar displaying the current quota percentage (e.g., `AG: 85%`).
2. Click the status bar icon to open the dropdown menu:
   - **Gemini Models Quota**: View Weekly and 5-Hour usage limits along with refresh countdowns.
   - **Claude & GPT Models Quota**: View model usage and reset timers.
   - **Launch at Login**: Click to toggle auto-start on macOS startup.
   - **Force Refresh**: Instantly query and update the quota data.

### Using the Chrome Extension
1. Click the Antigravity extension icon in your Chrome toolbar.
2. View your live quota status in a popup window.

---

## 🔧 Configuration & Customization

The backend server runs locally on port `8484` by default.

- **Backend Entry Point**: `backend/server.py`
- **Port Customization**: You can specify a custom port by passing an argument:
  ```bash
  python3 backend/server.py 8484
  ```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
