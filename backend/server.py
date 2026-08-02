import os
import pty
import subprocess
import time
import select
import sys
import fcntl
import termios
import struct
import re
import threading
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global Cache for Quota Data
quota_cache = {
    # Gemini models
    "gemini_weekly_percentage": 0.0,
    "gemini_weekly_remaining": "0% remaining",
    "gemini_weekly_refresh": "Unknown",
    "gemini_five_hour_percentage": 0.0,
    "gemini_five_hour_remaining": "0% remaining",
    "gemini_five_hour_refresh": "Unknown",
    
    # Claude/GPT models
    "claude_weekly_percentage": 0.0,
    "claude_weekly_remaining": "0% remaining",
    "claude_weekly_refresh": "Unknown",
    "claude_five_hour_percentage": 0.0,
    "claude_five_hour_remaining": "0% remaining",
    "claude_five_hour_refresh": "Unknown",
    
    "last_updated": 0,
    "status": "Initializing",
    "error_message": "",
    "error_type": "None",
    "cli_found": True,
    "cli_path": ""
}

cache_lock = threading.Lock()
history_lock = threading.Lock()
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(entry):
    with history_lock:
        history = load_history()
        history.append(entry)
        # Keep last 2016 data points (approx 7 days assuming 5-min intervals)
        if len(history) > 2016:
            history = history[-2016:]
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def set_pty_size(master_fd, rows, cols):
    try:
        s = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, s)
    except Exception:
        pass

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def format_refresh_time(refresh_str):
    if not refresh_str or refresh_str in ["--", "N/A", "Unknown"]:
        return refresh_str

    match_h = re.search(r'(\d+)\s*h', refresh_str, re.IGNORECASE)
    if match_h:
        total_hours = int(match_h.group(1))
        if total_hours >= 24:
            days = total_hours // 24
            rem_hours = total_hours % 24
            if rem_hours > 0:
                h_replacement = f"{days}d {rem_hours}h"
            else:
                h_replacement = f"{days}d"
            formatted = re.sub(r'\b' + match_h.group(1) + r'\s*h\b', h_replacement, refresh_str, flags=re.IGNORECASE)
            return formatted

    return refresh_str

def parse_section_robust(sec_text):
    sec_data = {
        "weekly_percentage": 0.0,
        "weekly_remaining": "Quota Available",
        "weekly_refresh": "--",
        "five_hour_percentage": 0.0,
        "five_hour_remaining": "Quota Available",
        "five_hour_refresh": "--"
    }
    
    if not sec_text or not sec_text.strip():
        return sec_data
        
    sec_lower = sec_text.lower()

    # 1. Weekly Limit Parsing
    weekly_pattern1 = re.compile(
        r'Weekly Limit\s*\n\s*\[[█░#=-]*\]\s*([\d.]+)%\s*\n\s*([^\n]+)', 
        re.MULTILINE | re.IGNORECASE
    )
    weekly_pattern2 = re.compile(
        r'Weekly[^\n]*?([\d.]+)%\s*\n?\s*([^\n]*)', 
        re.IGNORECASE
    )
    
    weekly_match = weekly_pattern1.search(sec_text) or weekly_pattern2.search(sec_text)
    if weekly_match:
        try:
            sec_data["weekly_percentage"] = float(weekly_match.group(1))
        except (ValueError, IndexError):
            pass
        
        if len(weekly_match.groups()) >= 2:
            details = weekly_match.group(2).strip()
            if "remaining" in details.lower() and "refreshes in" in details.lower():
                parts = details.split('·')
                sec_data["weekly_remaining"] = parts[0].strip()
                if len(parts) > 1:
                    sec_data["weekly_refresh"] = parts[1].replace('Refreshes in', '').replace('refreshes in', '').strip()
            else:
                sec_data["weekly_remaining"] = details if details else "Quota Available"
                sec_data["weekly_refresh"] = "--"
    elif "unlimited" in sec_lower or "no limit" in sec_lower:
        sec_data["weekly_remaining"] = "Unlimited Tier"
        sec_data["weekly_refresh"] = "N/A"

    # 2. Five Hour Limit Parsing
    five_hour_pattern1 = re.compile(
        r'Five Hour Limit\s*\n\s*\[[█░#=-]*\]\s*([\d.]+)%\s*\n\s*([^\n]+)', 
        re.MULTILINE | re.IGNORECASE
    )
    five_hour_pattern2 = re.compile(
        r'Five Hour[^\n]*?([\d.]+)%\s*\n?\s*([^\n]*)', 
        re.IGNORECASE
    )
    
    five_hour_match = five_hour_pattern1.search(sec_text) or five_hour_pattern2.search(sec_text)
    if five_hour_match:
        try:
            sec_data["five_hour_percentage"] = float(five_hour_match.group(1))
        except (ValueError, IndexError):
            pass
        
        if len(five_hour_match.groups()) >= 2:
            details = five_hour_match.group(2).strip()
            if "remaining" in details.lower() and "refreshes in" in details.lower():
                parts = details.split('·')
                sec_data["five_hour_remaining"] = parts[0].strip()
                if len(parts) > 1:
                    sec_data["five_hour_refresh"] = parts[1].replace('Refreshes in', '').replace('refreshes in', '').strip()
            else:
                sec_data["five_hour_remaining"] = details if details else "Quota Available"
                sec_data["five_hour_refresh"] = "--"
    elif "unlimited" in sec_lower or "no limit" in sec_lower:
        sec_data["five_hour_remaining"] = "Unlimited Tier"
        sec_data["five_hour_refresh"] = "N/A"

    sec_data["weekly_refresh"] = format_refresh_time(sec_data["weekly_refresh"])
    sec_data["five_hour_refresh"] = format_refresh_time(sec_data["five_hour_refresh"])

    # If Weekly Quota is completely exhausted (0% remaining / 100% used),
    # force 5-Hour Quota to 0% remaining (100% used) as it's effectively blocked.
    if sec_data["weekly_percentage"] == 0.0 and (
        "refreshes in" in sec_data["weekly_remaining"].lower() or 
        "remaining" in sec_data["weekly_remaining"].lower() or 
        sec_data["weekly_refresh"] != "--"
    ):
        sec_data["five_hour_percentage"] = 0.0
        sec_data["five_hour_remaining"] = "0% remaining (Weekly Depleted)"

    return sec_data

def parse_quota(text):
    parsed = {}
    gemini_sec = ""
    claude_sec = ""
    
    parts = re.split(r'CLAUDE AND GPT MODELS', text, flags=re.IGNORECASE)
    if len(parts) > 0:
        gemini_sec = parts[0]
    if len(parts) > 1:
        claude_sec = parts[1]
        
    gemini_data = parse_section_robust(gemini_sec)
    for k, v in gemini_data.items():
        parsed[f"gemini_{k}"] = v
        
    claude_data = parse_section_robust(claude_sec)
    for k, v in claude_data.items():
        parsed[f"claude_{k}"] = v
        
    return parsed

def fetch_quota_from_agy():
    master, slave = pty.openpty()
    set_pty_size(master, 120, 80)
    
    home_dir = os.path.expanduser("~")
    agy_path = os.path.join(home_dir, ".local/bin/agy")
    
    cli_found = True
    if not os.path.exists(agy_path):
        import shutil
        found_in_path = shutil.which("agy")
        if found_in_path:
            agy_path = found_in_path
        else:
            cli_found = False

    if not cli_found:
        os.close(slave)
        os.close(master)
        return {
            "error_type": "CLI_NOT_FOUND",
            "error_message": "agy executable not found at ~/.local/bin/agy or PATH",
            "cli_found": False,
            "cli_path": agy_path
        }
        
    env = os.environ.copy()
    env['TERM'] = 'xterm-256color'
    
    try:
        proc = subprocess.Popen(
            [agy_path, "--continue"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            cwd=home_dir,
            close_fds=True
        )
    except Exception as e:
        os.close(slave)
        os.close(master)
        return {
            "error_type": "EXEC_FAILED",
            "error_message": f"Failed to spawn agy process: {e}",
            "cli_found": True,
            "cli_path": agy_path
        }
        
    os.close(slave)
    
    def read_available(timeout=5):
        res = []
        start_time = time.time()
        while time.time() - start_time < timeout:
            r, _, _ = select.select([master], [], [], 0.2)
            if master in r:
                try:
                    data = os.read(master, 4096)
                    if not data:
                        break
                    res.append(data)
                    start_time = time.time()
                except OSError:
                    break
        return b"".join(res)
        
    try:
        time.sleep(3)
        startup_bytes = read_available(3)
        clean_startup = clean_ansi(startup_bytes.decode('utf-8', errors='ignore'))
        
        if "trust the contents" in clean_startup.lower() or "trust this folder" in clean_startup.lower():
            os.write(master, b"\r\n")
            time.sleep(1)
            read_available(2)
            
        poll = proc.poll()
        if poll is not None:
            return {
                "error_type": "PROCESS_EXITED",
                "error_message": f"agy exited early with code {poll}",
                "cli_found": True,
                "cli_path": agy_path
            }
            
        os.write(master, b"/usage\r\n")
        time.sleep(4)
        
        usage_bytes = read_available(4)
        raw_usage = usage_bytes.decode('utf-8', errors='ignore')
        clean_usage = clean_ansi(raw_usage)
        
        parsed = parse_quota(clean_usage)
        if not parsed:
            return {
                "error_type": "PARSING_FAILED",
                "error_message": "Could not parse quota structure from agy output",
                "cli_found": True,
                "cli_path": agy_path
            }
            
        os.write(master, b"/exit\r\n")
        time.sleep(0.5)
        
        parsed["error_type"] = "None"
        parsed["cli_found"] = True
        parsed["cli_path"] = agy_path
        return parsed
        
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            pass
        try:
            os.close(master)
        except Exception:
            pass

def quota_loader_loop():
    global quota_cache
    print("Background quota loader started.", flush=True)
    while True:
        try:
            print("Updating quota cache from agy...", flush=True)
            data = fetch_quota_from_agy()
            
            with cache_lock:
                if data.get("error_type", "None") != "None":
                    quota_cache["status"] = "Error"
                    quota_cache["error_type"] = data.get("error_type", "UNKNOWN_ERROR")
                    quota_cache["error_message"] = data.get("error_message", "Scraper encountered an error")
                    quota_cache["cli_found"] = data.get("cli_found", True)
                    quota_cache["cli_path"] = data.get("cli_path", "")
                else:
                    quota_cache.update(data)
                    quota_cache["last_updated"] = int(time.time())
                    quota_cache["status"] = "OK"
                    quota_cache["error_type"] = "None"
                    quota_cache["error_message"] = ""
                    
                    g_w_rem = quota_cache.get("gemini_weekly_percentage", 100.0)
                    g_5_rem = quota_cache.get("gemini_five_hour_percentage", 100.0)
                    c_w_rem = quota_cache.get("claude_weekly_percentage", 100.0)
                    c_5_rem = quota_cache.get("claude_five_hour_percentage", 100.0)

                    history_entry = {
                        "timestamp": quota_cache["last_updated"],
                        "gemini_weekly_used": round(max(0.0, 100.0 - g_w_rem), 1),
                        "gemini_five_hour_used": round(max(0.0, 100.0 - g_5_rem), 1),
                        "claude_weekly_used": round(max(0.0, 100.0 - c_w_rem), 1),
                        "claude_five_hour_used": round(max(0.0, 100.0 - c_5_rem), 1),

                        "gemini_weekly": round(max(0.0, 100.0 - g_w_rem), 1),
                        "gemini_five_hour": round(max(0.0, 100.0 - g_5_rem), 1),
                        "claude_weekly": round(max(0.0, 100.0 - c_w_rem), 1),
                        "claude_five_hour": round(max(0.0, 100.0 - c_5_rem), 1)
                    }
                    save_history(history_entry)
                    
            print(f"Quota cache status: {quota_cache['status']}", flush=True)
            
        except Exception as e:
            print(f"Error loading quota: {e}", flush=True)
            with cache_lock:
                quota_cache["status"] = "Error"
                quota_cache["error_type"] = "UNHANDLED_EXCEPTION"
                quota_cache["error_message"] = str(e)
                
        time.sleep(300)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity Quota Analytics Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-gemini: #38bdf8;
            --accent-claude: #a855f7;
            --accent-warning: #f59e0b;
            --accent-danger: #ef4444;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .container {
            width: 100%;
            max-width: 1100px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--card-border);
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 1.75rem;
            background: linear-gradient(135deg, var(--accent-gemini), var(--accent-claude));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .status-pill {
            background: rgba(56, 189, 248, 0.1);
            color: var(--accent-gemini);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #22c55e;
            box-shadow: 0 0 8px #22c55e;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.25rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
        }

        .card.gemini::before { background: linear-gradient(90deg, var(--accent-gemini), #818cf8); }
        .card.claude::before { background: linear-gradient(90deg, var(--accent-claude), #ec4899); }

        .card-header {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
        }

        .card-value-container {
            display: flex;
            align-items: baseline;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }

        .card-value {
            font-size: 2rem;
            font-weight: 700;
        }

        .card-value-label {
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 500;
        }

        .progress-bar-bg {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 9999px;
            overflow: hidden;
            margin-bottom: 0.75rem;
        }

        .progress-bar-fill {
            height: 100%;
            width: 0%;
            border-radius: 9999px;
            transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .card.gemini .progress-bar-fill { background: var(--accent-gemini); }
        .card.claude .progress-bar-fill { background: var(--accent-claude); }

        .card-footer {
            font-size: 0.8rem;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
        }

        .chart-section {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            margin-bottom: 2rem;
        }

        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
            flex-wrap: wrap;
            gap: 0.75rem;
        }

        .chart-title {
            font-size: 1.1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .chart-subtitle {
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 400;
        }

        /* Time Range Selector Buttons */
        .time-selector {
            display: flex;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 0.5rem;
            padding: 2px;
            gap: 2px;
        }

        .time-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.8rem;
            font-weight: 600;
            padding: 0.35rem 0.75rem;
            border-radius: 0.35rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .time-btn:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }

        .time-btn.active {
            background: var(--accent-gemini);
            color: #0f172a;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
        }

        .chart-container {
            position: relative;
            height: 340px;
            width: 100%;
        }

        footer {
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 1rem;
        }

        footer a {
            color: var(--accent-gemini);
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-group">
                <span class="logo-icon">📊</span>
                <h1>Antigravity Quota Analytics</h1>
            </div>
            <div class="status-pill">
                <span class="status-dot"></span>
                <span id="update-time">Updating...</span>
            </div>
        </header>

        <div class="grid">
            <!-- Gemini Weekly -->
            <div class="card gemini">
                <div class="card-header">
                    <span>Gemini Weekly</span>
                    <span>Used</span>
                </div>
                <div class="card-value-container">
                    <div class="card-value" id="g-weekly-val">--%</div>
                    <div class="card-value-label">Quota Used</div>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="g-weekly-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="g-weekly-rem">-- remaining</span>
                    <span id="g-weekly-ref">Reset: --</span>
                </div>
            </div>

            <!-- Gemini 5-Hour -->
            <div class="card gemini">
                <div class="card-header">
                    <span>Gemini 5-Hour</span>
                    <span>Used</span>
                </div>
                <div class="card-value-container">
                    <div class="card-value" id="g-5h-val">--%</div>
                    <div class="card-value-label">Quota Used</div>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="g-5h-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="g-5h-rem">-- remaining</span>
                    <span id="g-5h-ref">Reset: --</span>
                </div>
            </div>

            <!-- Claude Weekly -->
            <div class="card claude">
                <div class="card-header">
                    <span>Claude Weekly</span>
                    <span>Used</span>
                </div>
                <div class="card-value-container">
                    <div class="card-value" id="c-weekly-val">--%</div>
                    <div class="card-value-label">Quota Used</div>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="c-weekly-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="c-weekly-rem">-- remaining</span>
                    <span id="c-weekly-ref">Reset: --</span>
                </div>
            </div>

            <!-- Claude 5-Hour -->
            <div class="card claude">
                <div class="card-header">
                    <span>Claude 5-Hour</span>
                    <span>Used</span>
                </div>
                <div class="card-value-container">
                    <div class="card-value" id="c-5h-val">--%</div>
                    <div class="card-value-label">Quota Used</div>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="c-5h-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="c-5h-rem">-- remaining</span>
                    <span id="c-5h-ref">Reset: --</span>
                </div>
            </div>
        </div>

        <div class="chart-section">
            <div class="chart-header">
                <div class="chart-title">
                    <span>📈 Usage Trend History</span>
                    <span class="chart-subtitle">(Actual Consumption %)</span>
                </div>
                <!-- Time Range Buttons -->
                <div class="time-selector">
                    <button class="time-btn" onclick="setTimeRange('1H', this)">1H</button>
                    <button class="time-btn" onclick="setTimeRange('6H', this)">6H</button>
                    <button class="time-btn active" onclick="setTimeRange('24H', this)">24H</button>
                    <button class="time-btn" onclick="setTimeRange('7D', this)">7D</button>
                    <button class="time-btn" onclick="setTimeRange('ALL', this)">ALL</button>
                </div>
            </div>
            <div class="chart-container">
                <canvas id="trendChart"></canvas>
            </div>
        </div>

        <footer>
            Antigravity Quota Monitor &bull; Open Source on <a href="https://github.com/ktw1982-coder/antigravity-usage-extension" target="_blank">GitHub</a>
        </footer>
    </div>

    <script>
        let chartInstance = null;
        let cachedHistory = [];
        let currentRange = '24H';

        async function fetchMetrics() {
            try {
                const res = await fetch('/usage');
                const data = await res.json();

                const calcUsed = (remPct) => Math.max(0, Math.min(100, 100 - (remPct || 0)));

                // Gemini Weekly
                const gW_rem = data.gemini_weekly_percentage || 0;
                const gW_used = calcUsed(gW_rem);
                document.getElementById('g-weekly-val').textContent = `${gW_used.toFixed(1)}%`;
                document.getElementById('g-weekly-bar').style.width = `${gW_used}%`;
                document.getElementById('g-weekly-rem').textContent = data.gemini_weekly_remaining || 'Quota Available';
                document.getElementById('g-weekly-ref').textContent = `Reset: ${data.gemini_weekly_refresh || '--'}`;

                // Gemini 5-Hour
                const g5_rem = data.gemini_five_hour_percentage || 0;
                const g5_used = calcUsed(g5_rem);
                document.getElementById('g-5h-val').textContent = `${g5_used.toFixed(1)}%`;
                document.getElementById('g-5h-bar').style.width = `${g5_used}%`;
                document.getElementById('g-5h-rem').textContent = data.gemini_five_hour_remaining || 'Quota Available';
                document.getElementById('g-5h-ref').textContent = `Reset: ${data.gemini_five_hour_refresh || '--'}`;

                // Claude Weekly
                const cW_rem = data.claude_weekly_percentage || 0;
                const cW_used = calcUsed(cW_rem);
                document.getElementById('c-weekly-val').textContent = `${cW_used.toFixed(1)}%`;
                document.getElementById('c-weekly-bar').style.width = `${cW_used}%`;
                document.getElementById('c-weekly-rem').textContent = data.claude_weekly_remaining || 'Quota Available';
                document.getElementById('c-weekly-ref').textContent = `Reset: ${data.claude_weekly_refresh || '--'}`;

                // Claude 5-Hour
                const c5_rem = data.claude_five_hour_percentage || 0;
                const c5_used = calcUsed(c5_rem);
                document.getElementById('c-5h-val').textContent = `${c5_used.toFixed(1)}%`;
                document.getElementById('c-5h-bar').style.width = `${c5_used}%`;
                document.getElementById('c-5h-rem').textContent = data.claude_five_hour_remaining || 'Quota Available';
                document.getElementById('c-5h-ref').textContent = `Reset: ${data.claude_five_hour_refresh || '--'}`;

                if (data.last_updated) {
                    const d = new Date(data.last_updated * 1000);
                    document.getElementById('update-time').textContent = `Live: ${d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })}`;
                }
            } catch (err) {
                console.error("Failed to fetch current usage:", err);
            }
        }

        function filterHistoryByRange(history, range) {
            if (!history || history.length === 0) return [];
            const now = Math.floor(Date.now() / 1000);
            
            let secondsCutoff = 86400; // default 24h
            if (range === '1H') secondsCutoff = 3600;
            else if (range === '6H') secondsCutoff = 21600;
            else if (range === '24H') secondsCutoff = 86400;
            else if (range === '7D') secondsCutoff = 604800;
            else if (range === 'ALL') secondsCutoff = Infinity;

            return history.filter(h => (now - h.timestamp) <= secondsCutoff);
        }

        function setTimeRange(range, btnElement) {
            currentRange = range;
            document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));
            if (btnElement) {
                btnElement.classList.add('active');
            }
            renderChart(cachedHistory);
        }

        function renderChart(historyData) {
            const filtered = filterHistoryByRange(historyData, currentRange);

            const labels = filtered.map(h => {
                const d = new Date(h.timestamp * 1000);
                if (currentRange === '1H' || currentRange === '6H' || currentRange === '24H') {
                    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
                } else {
                    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:00`;
                }
            });

            const gWeeklyUsed = filtered.map(h => h.gemini_weekly_used !== undefined ? h.gemini_weekly_used : (h.gemini_weekly || 0));
            const gFiveHourUsed = filtered.map(h => h.gemini_five_hour_used !== undefined ? h.gemini_five_hour_used : (h.gemini_five_hour || 0));
            const cWeeklyUsed = filtered.map(h => h.claude_weekly_used !== undefined ? h.claude_weekly_used : (h.claude_weekly || 0));
            const cFiveHourUsed = filtered.map(h => h.claude_five_hour_used !== undefined ? h.claude_five_hour_used : (h.claude_five_hour || 0));

            const ctx = document.getElementById('trendChart').getContext('2d');

            if (chartInstance) {
                chartInstance.destroy();
            }

            chartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels.length > 0 ? labels : ['Now'],
                    datasets: [
                        {
                            label: 'Gemini Weekly Used %',
                            data: gWeeklyUsed.length > 0 ? gWeeklyUsed : [0],
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.15)',
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5
                        },
                        {
                            label: 'Gemini 5-Hour Used %',
                            data: gFiveHourUsed.length > 0 ? gFiveHourUsed : [0],
                            borderColor: '#818cf8',
                            backgroundColor: 'transparent',
                            borderDash: [4, 4],
                            tension: 0.35,
                            borderWidth: 2
                        },
                        {
                            label: 'Claude Weekly Used %',
                            data: cWeeklyUsed.length > 0 ? cWeeklyUsed : [0],
                            borderColor: '#a855f7',
                            backgroundColor: 'rgba(168, 85, 247, 0.15)',
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5
                        },
                        {
                            label: 'Claude 5-Hour Used %',
                            data: cFiveHourUsed.length > 0 ? cFiveHourUsed : [0],
                            borderColor: '#ec4899',
                            backgroundColor: 'transparent',
                            borderDash: [4, 4],
                            tension: 0.35,
                            borderWidth: 2
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {
                        duration: 400
                    },
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#94a3b8' }
                        },
                        y: {
                            min: 0,
                            max: 100,
                            title: {
                                display: true,
                                text: 'Quota Used (%)',
                                color: '#94a3b8'
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: {
                                color: '#94a3b8',
                                callback: function(val) { return val + '%'; }
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: { color: '#f8fafc', font: { family: 'Inter' } }
                        },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            titleColor: '#f8fafc',
                            bodyColor: '#94a3b8',
                            borderColor: '#334155',
                            borderWidth: 1,
                            callbacks: {
                                label: function(context) {
                                    return `${context.dataset.label}: ${context.raw}% Used`;
                                }
                            }
                        }
                    }
                }
            });
        }

        async function fetchHistoryAndRenderChart() {
            try {
                const res = await fetch('/history');
                cachedHistory = await res.json();
                renderChart(cachedHistory);
            } catch (err) {
                console.error("Failed to fetch history:", err);
            }
        }

        // Init
        fetchMetrics();
        fetchHistoryAndRenderChart();

        // Refresh periodically
        setInterval(fetchMetrics, 10000);
        setInterval(fetchHistoryAndRenderChart, 60000);
    </script>
</body>
</html>
"""

class QuotaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        if path in ['/', '/dashboard']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
            
        elif path == '/usage':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            with cache_lock:
                response_data = json.dumps(quota_cache)
                
            self.wfile.write(response_data.encode('utf-8'))
            
        elif path == '/history':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            history_data = load_history()
            self.wfile.write(json.dumps(history_data).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def parent_watcher(parent_pid):
    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watcher.log")
    try:
        with open(log_file_path, "w") as f:
            f.write(f"Watcher thread started. Target parent PID: {parent_pid}\n")
            f.flush()
    except Exception:
        pass

    while True:
        try:
            os.kill(parent_pid, 0)
        except OSError:
            try:
                with open(log_file_path, "a") as f:
                    f.write(f"Ping parent {parent_pid}: Dead. Terminating process...\n")
                    f.flush()
            except Exception:
                pass
            os._exit(0)
        time.sleep(2)

def run_server(port=8484, parent_pid=None):
    if parent_pid is not None:
        watcher_thread = threading.Thread(target=parent_watcher, args=(parent_pid,), daemon=True)
        watcher_thread.start()

    loader_thread = threading.Thread(target=quota_loader_loop, daemon=True)
    loader_thread.start()
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, QuotaHandler)
    print(f"Server running on port {port}...", flush=True)
    print(f"Dashboard available at http://localhost:{port}/dashboard", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("Server stopped.", flush=True)

if __name__ == '__main__':
    port = 8484
    parent_pid = None
    
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
            
    if len(sys.argv) > 2:
        try:
            parent_pid = int(sys.argv[2])
        except ValueError:
            pass
            
    run_server(port, parent_pid)
