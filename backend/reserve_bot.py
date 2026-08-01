import sys
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

def get_current_time_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def run_bot(svc_id, target_date, target_time_index, open_time_str):
    """
    svc_id: Seoul Reservation Service ID (e.g. S220325100057463252)
    target_date: Target reservation date in YYYYMMDD format (e.g. 20260725)
    target_time_index: Time slot index to select (e.g. 1 for the first available slot)
    open_time_str: Ticketing start time in HH:MM:SS format (e.g. 13:30:00)
    """
    
    target_url = f"https://yeyak.seoul.go.kr/web/reservation/selectReservView.do?rsv_svc_id={svc_id}"
    
    print("====================================================")
    print("      SEOUL PUBLIC RESERVATION AUTOMATION BOT")
    print("====================================================")
    print(f"[*] Target URL: {target_url}")
    print(f"[*] Target Date: {target_date}")
    print(f"[*] Target Time Slot Index: {target_time_index}")
    print(f"[*] Target Ticketing Open Time: {open_time_str}")
    print("====================================================")
    
    with sync_playwright() as p:
        print("[*] Launching Chromium browser...")
        # Launch browser in headful mode so the user can log in manually
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        print("[*] Navigating to reservation page...")
        page.goto(target_url)
        
        # 1. Login session verification loop
        print("\n[!] Please log in to your Seoul Portal account in the browser window.")
        print("[*] Watching for active session (waiting for logout button to appear)...")
        
        logged_in = False
        while not logged_in:
            try:
                # If logout href is present, user is logged in
                logout_btn = page.query_selector('a[href*="logout.do"]')
                if logout_btn:
                    print("[+] Login detected successfully!")
                    logged_in = True
                    break
            except Exception:
                pass
            time.sleep(1)
            
        print("[*] Session active. Returning to target reservation page...")
        page.goto(target_url)
        page.wait_for_load_state("networkidle")
        
        # 2. Wait for ticketing open time
        if open_time_str:
            target_time = datetime.strptime(open_time_str, "%H:%M:%S").time()
            print(f"\n[*] Waiting for target ticketing opening time: {open_time_str}...")
            
            while True:
                now = datetime.now()
                # Check if we are within 2 seconds of the opening time to start fast refresh
                time_diff = (datetime.combine(now.date(), target_time) - now).total_seconds()
                
                if time_diff <= 2.0 and time_diff > 0:
                    print(f"[{get_current_time_str()}] Entering fast-refresh window (2s before open)...")
                    # Sleep exactly until 0.3 seconds before opening to do the first refresh
                    time.sleep(max(0.0, time_diff - 0.3))
                    break
                elif time_diff <= 0:
                    # Opening time has already passed
                    break
                
                print(f"[{get_current_time_str()}] Waiting... (Current server/local time)")
                time.sleep(1)
                
            # Perform instant page refresh just at the opening time
            print(f"[{get_current_time_str()}] 🔄 Refreshing page for ticketing activation...")
            page.reload()
            page.wait_for_load_state("domcontentloaded")
            
        # 3. Fast button click loop (evaluate JS directly to bypass animations)
        print(f"\n[{get_current_time_str()}] Searching for '예약하기' button...")
        clicked = False
        start_click_time = time.time()
        
        # Keep searching for 10 seconds or until clicked
        while time.time() - start_click_time < 10:
            # Check if button or its JS function is ready
            btn = page.query_selector('a:has-text("예약하기"), a[href*="fnRevervInsertForm"]')
            if btn:
                print(f"[{get_current_time_str()}] [+] Button found! Clicking via JS evaluation...")
                # Directly execute the script function to enter reservation form immediately
                page.evaluate("fnRevervInsertForm()")
                clicked = True
                break
            time.sleep(0.1)
            
        if not clicked:
            print("[❌] Failed to find the booking button. Please check if ticketing is open.")
            browser.close()
            return
            
        # 4. Wait for reservation input form to load
        print(f"[{get_current_time_str()}] Waiting for reservation form/calendar load...")
        try:
            # Wait for calendar table or date picker
            page.wait_for_selector(".tbl_cal, #calendar, input[type='checkbox']", timeout=5000)
        except Exception:
            print("[!] Timeout waiting for input selectors. Attempting manual flow integration...")
            
        # 5. Date Selection
        print(f"[{get_current_time_str()}] Selecting target date: {target_date}...")
        date_selected = False
        # Find date links matching target date in calendar (e.g. fnSelectDate('20260720'))
        date_elements = page.query_selector_all(f"a[href*='{target_date}'], td[onclick*='{target_date}']")
        if date_elements:
            print(f"[+] Date selectors matching {target_date} found. Clicking...")
            date_elements[0].click()
            date_selected = True
        else:
            # Fallback: look for calendar days with text matching day part of YYYYMMDD
            day_str = str(int(target_date[-2:])) # e.g. "05" -> "5"
            day_elements = page.query_selector_all(f"a:text-is('{day_str}'), td:has-text('{day_str}')")
            for day_el in day_elements:
                if "예약불가" not in (day_el.get_attribute("title") or ""):
                    day_el.click()
                    date_selected = True
                    break
                    
        if not date_selected:
            print(f"[⚠️] Could not select date {target_date} automatically. Please click it manually in the window!")
            
        # 6. Automatic check-all agreements
        print(f"[{get_current_time_str()}] Checking all essential agreements...")
        checkboxes = page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            if not cb.is_checked():
                try:
                    cb.click()
                except Exception:
                    pass
                    
        # 7. Safe boundary warning (Stop before final submission for safety)
        print("\n====================================================")
        print("          AUTOMATIC FORM POPULATION COMPLETE")
        print("====================================================")
        print("[!] For safety, the bot has NOT submitted the final booking.")
        print("[!] Please select your preferred time slot and click submit manually.")
        print("[*] Keeping the browser window open. Press Ctrl+C in terminal to exit.")
        print("====================================================")
        
        # Keep open
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Exiting bot. Closing browser...")
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seoul Public Reservation Auto Booking Bot")
    parser.add_argument("--svc_id", type=str, default="S220325100057463252", help="Seoul Reservation Service ID")
    parser.add_argument("--date", type=str, required=True, help="Target booking date in YYYYMMDD format (e.g. 20260715)")
    parser.add_argument("--slot", type=int, default=1, help="Time slot index (default: 1)")
    parser.add_argument("--open_time", type=str, default="", help="Ticketing open time in HH:MM:SS format (e.g. 13:30:00)")
    
    args = parser.parse_args()
    
    # Verify input format
    if len(args.date) != 8 or not args.date.isdigit():
        print("[❌] Error: Date must be YYYYMMDD format (8 digits).")
        sys.exit(1)
        
    try:
        run_bot(args.svc_id, args.date, args.slot, args.open_time)
    except Exception as e:
        print(f"[❌] Fatal Script Error: {e}")
