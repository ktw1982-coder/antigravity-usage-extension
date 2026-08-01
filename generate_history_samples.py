import json
import os
import time
import math

def generate_sample_history():
    history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "history.json")
    
    now = int(time.time())
    five_min = 300
    total_points = 288 * 7  # 7 days of data (2016 points)
    
    samples = []
    
    for i in range(total_points, 0, -1):
        ts = now - (i * five_min)
        
        # Simulate realistic usage wave
        hour = (ts // 3600) % 24
        day_of_week = (ts // 86400) % 7
        
        # Base activity higher during work hours (09:00 - 22:00)
        if 9 <= hour <= 22:
            base_gemini = 20.0 + 35.0 * math.sin((i / 20.0)) + (hour - 9) * 2.5
            base_claude = 15.0 + 25.0 * math.cos((i / 15.0)) + (hour - 9) * 1.8
        else:
            base_gemini = 10.0 + 5.0 * math.sin((i / 30.0))
            base_claude = 5.0 + 3.0 * math.cos((i / 30.0))
            
        gemini_used = round(max(0.0, min(95.0, base_gemini)), 1)
        claude_used = round(max(0.0, min(95.0, base_claude)), 1)
        
        samples.append({
            "timestamp": ts,
            "gemini_weekly_used": gemini_used,
            "gemini_five_hour_used": round(max(0.0, min(100.0, gemini_used * 0.4)), 1),
            "claude_weekly_used": claude_used,
            "claude_five_hour_used": round(max(0.0, min(100.0, claude_used * 0.3)), 1),
            
            "gemini_weekly": gemini_used,
            "gemini_five_hour": round(max(0.0, min(100.0, gemini_used * 0.4)), 1),
            "claude_weekly": claude_used,
            "claude_five_hour": round(max(0.0, min(100.0, claude_used * 0.3)), 1)
        })
        
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
        
    print(f"Generated {len(samples)} sample history points into {history_file}")

if __name__ == "__main__":
    generate_sample_history()
