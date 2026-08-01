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
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global Cache for Quota Data containing both Gemini and Claude/GPT models
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
    "error_message": ""
}

cache_lock = threading.Lock()

def set_pty_size(master_fd, rows, cols):
    s = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, s)

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def parse_quota(text):
    parsed = {}
    
    # Split text into Gemini and Claude/GPT sections
    gemini_sec = ""
    claude_sec = ""
    
    parts = text.split("CLAUDE AND GPT MODELS")
    if len(parts) > 0:
        gemini_sec = parts[0]
    if len(parts) > 1:
        claude_sec = parts[1]
        
    def parse_section(sec_text):
        sec_data = {
            "weekly_percentage": 0.0,
            "weekly_remaining": "0% remaining",
            "weekly_refresh": "Unknown",
            "five_hour_percentage": 0.0,
            "five_hour_remaining": "0% remaining",
            "five_hour_refresh": "Unknown"
        }
        
        # Weekly Limit Parsing (Generalized to match any info string below percentage)
        weekly_pattern = re.compile(
            r'Weekly Limit\s*\n\s*\[[█░]+\]\s*([\d.]+)%\s*\n\s*([^\n]+)', 
            re.MULTILINE
        )
        weekly_match = weekly_pattern.search(sec_text)
        if weekly_match:
            sec_data["weekly_percentage"] = float(weekly_match.group(1))
            details = weekly_match.group(2).strip()
            if "remaining" in details and "Refreshes in" in details:
                parts = details.split('·')
                sec_data["weekly_remaining"] = parts[0].strip()
                if len(parts) > 1:
                    sec_data["weekly_refresh"] = parts[1].replace('Refreshes in', '').strip()
            else:
                sec_data["weekly_remaining"] = details  # e.g., "Quota available" or other state
                sec_data["weekly_refresh"] = "--"
                
        # Five Hour Limit Parsing (Generalized to match any info string below percentage)
        five_hour_pattern = re.compile(
            r'Five Hour Limit\s*\n\s*\[[█░]+\]\s*([\d.]+)%\s*\n\s*([^\n]+)', 
            re.MULTILINE
        )
        five_hour_match = five_hour_pattern.search(sec_text)
        if five_hour_match:
            sec_data["five_hour_percentage"] = float(five_hour_match.group(1))
            details = five_hour_match.group(2).strip()
            if "remaining" in details and "Refreshes in" in details:
                parts = details.split('·')
                sec_data["five_hour_remaining"] = parts[0].strip()
                if len(parts) > 1:
                    sec_data["five_hour_refresh"] = parts[1].replace('Refreshes in', '').strip()
            else:
                sec_data["five_hour_remaining"] = details  # e.g., "Quota available" or other state
                sec_data["five_hour_refresh"] = "--"
                
        return sec_data

    # Parse Gemini section
    gemini_data = parse_section(gemini_sec)
    for k, v in gemini_data.items():
        parsed[f"gemini_{k}"] = v
        
    # Parse Claude/GPT section
    claude_data = parse_section(claude_sec)
    for k, v in claude_data.items():
        parsed[f"claude_{k}"] = v
        
    return parsed

def fetch_quota_from_agy():
    master, slave = pty.openpty()
    set_pty_size(master, 120, 80)
    
    home_dir = os.path.expanduser("~")
    agy_path = os.path.join(home_dir, ".local/bin/agy")
    if not os.path.exists(agy_path):
        agy_path = "agy"
        
    env = os.environ.copy()
    env['TERM'] = 'xterm-256color'
    
    proc = subprocess.Popen(
        [agy_path, "--continue"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=home_dir,
        close_fds=True
    )
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
        
        if "trust the contents" in clean_startup or "trust this folder" in clean_startup:
            os.write(master, b"\r\n")
            time.sleep(1)
            read_available(2)
            
        poll = proc.poll()
        if poll is not None:
            raise Exception(f"agy process exited early with code {poll}")
            
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
        except:
            pass
        
        parsed = parse_quota(clean_usage)
        if not parsed:
            raise Exception("Failed to parse quota information from output.")
            
        os.write(master, b"/exit\r\n")
        time.sleep(0.5)
        
        return parsed
        
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except:
            pass
        os.close(master)

def quota_loader_loop():
    global quota_cache
    print("Background quota loader started.", flush=True)
    while True:
        try:
            print("Updating quota cache from agy...", flush=True)
            data = fetch_quota_from_agy()
            
            with cache_lock:
                quota_cache.update(data)
                quota_cache["last_updated"] = int(time.time())
                quota_cache["status"] = "OK"
                quota_cache["error_message"] = ""
            print("Quota cache successfully updated.", flush=True)
            
        except Exception as e:
            print(f"Error loading quota: {e}", flush=True)
            with cache_lock:
                quota_cache["status"] = "Error"
                quota_cache["error_message"] = str(e)
                
        time.sleep(300)

class QuotaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        if self.path == '/usage':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            with cache_lock:
                response_data = json.dumps(quota_cache)
                
            self.wfile.write(response_data.encode('utf-8'))
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
    except:
        pass

    while True:
        try:
            os.kill(parent_pid, 0)
        except OSError:
            try:
                with open(log_file_path, "a") as f:
                    f.write(f"Ping parent {parent_pid}: Dead. Terminating process...\n")
                    f.flush()
            except:
                pass
            os._exit(0)
        time.sleep(2)

def run_server(port=8484, parent_pid=None):
    if parent_pid is not None:
        watcher_thread = threading.Thread(target=parent_watcher, args=(parent_pid,), daemon=True)
        watcher_thread.start()

    # Start the background status scraper thread
    loader_thread = threading.Thread(target=quota_loader_loop, daemon=True)
    loader_thread.start()
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, QuotaHandler)
    print(f"Server running on port {port}...", flush=True)
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
