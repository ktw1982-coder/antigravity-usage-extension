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

# Global Cache for Quota Data containing detailed error types & fallback info
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
        # Keep last 288 data points (approx 24 hours assuming 5-min intervals)
        if len(history) > 288:
            history = history[-288:]
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
        
        try:
            raw_usage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_usage.txt")
            with open(raw_usage_path, "w") as f:
                f.write(clean_usage)
                f.flush()
        except Exception:
            pass
        
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
                    
                    # Record history entry for Trend Chart
                    history_entry = {
                        "timestamp": quota_cache["last_updated"],
                        "gemini_weekly": quota_cache.get("gemini_weekly_percentage", 0.0),
                        "gemini_five_hour": quota_cache.get("gemini_five_hour_percentage", 0.0),
                        "claude_weekly": quota_cache.get("claude_weekly_percentage", 0.0),
                        "claude_five_hour": quota_cache.get("claude_five_hour_percentage", 0.0)
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
        }

        .card-value {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
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
        }

        .chart-title {
            font-size: 1.1rem;
            font-weight: 600;
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
            <div class="card gemini">
                <div class="card-header">Gemini Weekly Quota</div>
                <div class="card-value" id="g-weekly-val">--%</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="g-weekly-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="g-weekly-rem">0% remaining</span>
                    <span id="g-weekly-ref">Refreshes: --</span>
                </div>
            </div>

            <div class="card gemini">
                <div class="card-header">Gemini 5-Hour Quota</div>
                <div class="card-value" id="g-5h-val">--%</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="g-5h-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="g-5h-rem">0% remaining</span>
                    <span id="g-5h-ref">Refreshes: --</span>
                </div>
            </div>

            <div class="card claude">
                <div class="card-header">Claude Weekly Quota</div>
                <div class="card-value" id="c-weekly-val">--%</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="c-weekly-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="c-weekly-rem">0% remaining</span>
                    <span id="c-weekly-ref">Refreshes: --</span>
                </div>
            </div>

            <div class="card claude">
                <div class="card-header">Claude 5-Hour Quota</div>
                <div class="card-value" id="c-5h-val">--%</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="c-5h-bar"></div>
                </div>
                <div class="card-footer">
                    <span id="c-5h-rem">0% remaining</span>
                    <span id="c-5h-ref">Refreshes: --</span>
                </div>
            </div>
        </div>

        <div class="chart-section">
            <div class="chart-header">
                <div class="chart-title">📈 24-Hour Usage Trend History</div>
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

        async function fetchMetrics() {
            try {
                const res = await fetch('/usage');
                const data = await res.json();

                // Gemini
                const gW = data.gemini_weekly_percentage || 0;
                document.getElementById('g-weekly-val').textContent = `${gW.toFixed(1)}%`;
                document.getElementById('g-weekly-bar').style.width = `${gW}%`;
                document.getElementById('g-weekly-rem').textContent = data.gemini_weekly_remaining || '0% remaining';
                document.getElementById('g-weekly-ref').textContent = `Reset: ${data.gemini_weekly_refresh || '--'}`;

                const g5 = data.gemini_five_hour_percentage || 0;
                document.getElementById('g-5h-val').textContent = `${g5.toFixed(1)}%`;
                document.getElementById('g-5h-bar').style.width = `${g5}%`;
                document.getElementById('g-5h-rem').textContent = data.gemini_five_hour_remaining || '0% remaining';
                document.getElementById('g-5h-ref').textContent = `Reset: ${data.gemini_five_hour_refresh || '--'}`;

                // Claude
                const cW = data.claude_weekly_percentage || 0;
                document.getElementById('c-weekly-val').textContent = `${cW.toFixed(1)}%`;
                document.getElementById('c-weekly-bar').style.width = `${cW}%`;
                document.getElementById('c-weekly-rem').textContent = data.claude_weekly_remaining || '0% remaining';
                document.getElementById('c-weekly-ref').textContent = `Reset: ${data.claude_weekly_refresh || '--'}`;

                const c5 = data.claude_five_hour_percentage || 0;
                document.getElementById('c-5h-val').textContent = `${c5.toFixed(1)}%`;
                document.getElementById('c-5h-bar').style.width = `${c5}%`;
                document.getElementById('c-5h-rem').textContent = data.claude_five_hour_remaining || '0% remaining';
                document.getElementById('c-5h-ref').textContent = `Reset: ${data.claude_five_hour_refresh || '--'}`;

                if (data.last_updated) {
                    const d = new Date(data.last_updated * 1000);
                    document.getElementById('update-time').textContent = `Live: ${d.toLocaleTimeString()}`;
                }
            } catch (err) {
                console.error("Failed to fetch current usage:", err);
            }
        }

        async function fetchHistoryAndRenderChart() {
            try {
                const res = await fetch('/history');
                const history = await res.json();

                const labels = history.map(h => {
                    const d = new Date(h.timestamp * 1000);
                    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                });

                const gWeeklyData = history.map(h => h.gemini_weekly || 0);
                const gFiveHourData = history.map(h => h.gemini_five_hour || 0);
                const cWeeklyData = history.map(h => h.claude_weekly || 0);
                const cFiveHourData = history.map(h => h.claude_five_hour || 0);

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
                                label: 'Gemini Weekly %',
                                data: gWeeklyData.length > 0 ? gWeeklyData : [0],
                                borderColor: '#38bdf8',
                                backgroundColor: 'rgba(56, 189, 248, 0.1)',
                                fill: true,
                                tension: 0.35,
                                borderWidth: 2.5
                            },
                            {
                                label: 'Gemini 5-Hour %',
                                data: gFiveHourData.length > 0 ? gFiveHourData : [0],
                                borderColor: '#818cf8',
                                backgroundColor: 'transparent',
                                borderDash: [4, 4],
                                tension: 0.35,
                                borderWidth: 2
                            },
                            {
                                label: 'Claude Weekly %',
                                data: cWeeklyData.length > 0 ? cWeeklyData : [0],
                                borderColor: '#a855f7',
                                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                                fill: true,
                                tension: 0.35,
                                borderWidth: 2.5
                            },
                            {
                                label: 'Claude 5-Hour %',
                                data: cFiveHourData.length > 0 ? cFiveHourData : [0],
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
                                borderWidth: 1
                            }
                        }
                    }
                });
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
