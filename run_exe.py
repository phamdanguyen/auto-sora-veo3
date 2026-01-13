import uvicorn
import os
import sys
import threading
import time
import subprocess
import socket
import webview
import traceback

# --- CRITICAL STARTUP LOGGING ---
LOG_FILE = "startup_log.txt"

def log_startup(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except:
        pass
    print(msg)

def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_startup(f"CRITICAL UNHANDLED EXCEPTION:\n{error_msg}")
    print("CRITICAL ERROR:", error_msg)
    input("Press Enter to exit...") # Keep console open

sys.excepthook = global_exception_handler

log_startup("=== NEW STARTUP SESSION ===")
log_startup(f"CWD: {os.getcwd()}")
log_startup(f"Executable: {sys.executable}")
if getattr(sys, 'frozen', False):
    log_startup(f"Running in FROZEN mode. MEIPASS: {getattr(sys, '_MEIPASS', 'Not Set')}")
else:
    log_startup("Running in SCRIPT mode.")
log_startup(f"Path: {sys.path}")
# ------------------------------
# from app.main import app # Moved to inside functions to prevent import errors crashing the app before logging

def check_and_install_playwright():
    """Check if Playwright browsers are installed, install if needed."""
    try:
        from playwright.sync_api import sync_playwright
        # Quick check if chromium is available
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("✅ Playwright browsers ready.")
                return True
            except Exception as e:
                print(f"⚠️ Playwright browser not found. Installing...")
    except ImportError:
        print("⚠️ Playwright not installed.")
        return False
    
    # Try to install browsers
    try:
        if getattr(sys, 'frozen', False):
            print("⚠️ Running in frozen mode. Cannot auto-install Playwright browsers.")
            print("   Please install them manually if missing: pip install playwright && playwright install chromium")
            return False
            
        print("📥 Installing Playwright Chromium browser...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Playwright Chromium installed successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to install Playwright: {e}")
        return False

def find_free_port(start_port=8001, max_port=8100):
    """
    Finds a free port within a specific range.
    """
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise IOError(f"No free ports found between {start_port} and {max_port}")

def start_server(port):
    """Starts the FastAPI server in a background thread."""
    try:
        log_message(f"DEBUG: Entering start_server thread for port {port}")
        from app.main import app
        from app.core.logger import ListLogHandler
        import logging
        
        log_message("DEBUG: app.main imported successfully")
        
        # Configure logging to capture Uvicorn logs
        # Get the root logger or uvicorn logger
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.addHandler(ListLogHandler())
        
        # Also capture FastAPI/App logs
        root_logger = logging.getLogger()
        root_logger.addHandler(ListLogHandler())
        
        # Run uvicorn Programmatically
        # log_level can be set to "debug" for more info if needed
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        log_message("DEBUG: uvicorn.run finished (server stopped?)")
    except Exception as e:
        log_message(f"CRITICAL ERROR in server thread: {e}")
        import traceback
        log_message(traceback.format_exc())

def on_closed():
    """Handler for when the window is closed."""
    log_message("App window closed. Shutting down...")
    os._exit(0)


# --- CONFIGURATION ---
LOG_FILE = "debug_log.txt"

# Add parent directory to path to import app modules if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.core.logger import log_manager
except ImportError:
    log_manager = None
    import datetime

def log_message(message):
    """Logs a message to the file, console, and LogStreamManager."""
    try:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    except:
        timestamp = "UNKNOWN_TIME"
        
    formatted_message = f"{timestamp} - {message}"
    
    # 1. Write to file
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_message + "\n")
    except:
        pass
        
    # 2. Print to console
    print(formatted_message)
    
    # 3. Stream to WebSocket Manager
    if log_manager:
        log_manager.add_log(formatted_message, "INFO")

if __name__ == "__main__":
    try:
        # Clear previous log
        with open("debug_log.txt", "w", encoding="utf-8") as f:
            f.write("=== Application Startup ===\n")

        log_message("Starting Uni-Video Automation (GUI Mode)")
        
        # --- LICENSE CHECK ---
        log_message("Checking License...")
        try:
            from app.core.license_manager import LicenseManager
            import tkinter as tk
            from tkinter import simpledialog, messagebox
            
            status_info = LicenseManager.get_license_status()
            status = status_info["status"]
            hwid = status_info["hardware_id"]
            
            if status != "valid":
                log_message(f"License check failed: {status} - {status_info['message']}")
                
                # Custom License Dialog Function
                def get_license_key_ui(hwid_val, status_msg):
                    result_container = {"key": None}
                    
                    win = tk.Tk()
                    win.title("Uni-Video License Activation")
                    # Center the window
                    w, h = 500, 300
                    try:
                        ws = win.winfo_screenwidth()
                        hs = win.winfo_screenheight()
                        x = (ws/2) - (w/2)
                        y = (hs/2) - (h/2)
                        win.geometry('%dx%d+%d+%d' % (w, h, x, y))
                    except:
                        win.geometry("500x300")
                    
                    # Prevent resizing
                    win.resizable(False, False)

                    # UI Elements
                    tk.Label(win, text="Uni-Video Automation", font=("Segoe UI", 16, "bold")).pack(pady=(15, 5))
                    tk.Label(win, text=status_msg, fg="red", font=("Segoe UI", 10)).pack(pady=5)
                    
                    # HWID Section
                    tk.Label(win, text="Your Hardware ID (Copy this to Admin):", font=("Segoe UI", 9)).pack(anchor="w", padx=30)
                    
                    f_hwid = tk.Frame(win)
                    f_hwid.pack(fill="x", padx=30, pady=2)
                    
                    entry_hwid = tk.Entry(f_hwid, font=("Consolas", 10), bg="#f0f0f0")
                    entry_hwid.insert(0, hwid_val)
                    entry_hwid.config(state='readonly')
                    entry_hwid.pack(side=tk.LEFT, fill="x", expand=True)
                    
                    def copy_hwid():
                        win.clipboard_clear()
                        win.clipboard_append(hwid_val)
                        messagebox.showinfo("Copied", "Hardware ID copied to clipboard!", parent=win)
                        
                    tk.Button(f_hwid, text="Copy", command=copy_hwid).pack(side=tk.LEFT, padx=(5, 0))
                    
                    # Key Input Section
                    tk.Label(win, text="Enter License Key:", font=("Segoe UI", 9)).pack(anchor="w", padx=30, pady=(15, 2))
                    entry_key = tk.Entry(win, font=("Consolas", 9))
                    entry_key.pack(fill="x", padx=30)
                    entry_key.focus_set()
                    
                    def on_submit(event=None):
                        key_val = entry_key.get().strip()
                        if not key_val:
                            return
                        
                        # Validate immediately
                        valid, v_msg, v_exp = LicenseManager.validate_key(key_val)
                        if valid:
                            LicenseManager.save_key(key_val)
                            messagebox.showinfo("Success", f"License Activated!\nExpires: {v_exp}", parent=win)
                            result_container["key"] = key_val
                            win.destroy()
                        else:
                            messagebox.showerror("Invalid Key", f"Error: {v_msg}", parent=win)
                            
                    def on_trial():
                        # Fix: Import datetime at the top of the function scope
                        from datetime import datetime, timedelta
                        
                        # Check for existing trial marker
                        marker_path = os.path.join(os.path.expanduser("~"), ".univideo_trial_marker")
                        
                        trial_still_active = False
                        remaining_days = 0
                        
                        if os.path.exists(marker_path):
                            try:
                                with open(marker_path, "r") as f:
                                    content = f.read().strip()
                                    if "used_on=" in content:
                                        date_str = content.split("used_on=")[1].strip()
                                        # Handle potential format variations
                                        try:
                                            # Try parsing standard str(datetime) format
                                            start_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
                                        except ValueError:
                                            try:
                                                # Failover for cases without microseconds
                                                start_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                                            except:
                                                start_date = None
                                        
                                        if start_date:
                                            # Calculate expiration
                                            expiry_date = start_date + timedelta(days=7)
                                            now = datetime.utcnow()
                                            
                                            if now < expiry_date:
                                                trial_still_active = True
                                                remaining_days = (expiry_date - now).days + 1
                                                
                                                if messagebox.askyesno("Trial Active", f"Trial is still active! ({remaining_days} days remaining).\nDo you want to restore your trial license?", parent=win):
                                                    pass 
                                                else:
                                                    return
                                            else:
                                                messagebox.showerror("Trial Expired", f"Your trial expired on {expiry_date.strftime('%Y-%m-%d')}.", parent=win)
                                                return
                                    else:
                                         messagebox.showerror("Trial Expired", "Trial marker found (invalid data).", parent=win)
                                         return
                            except Exception as e:
                                log_message(f"Error reading trial marker: {e}")
                                messagebox.showerror("Trial Error", "Could not verify trial status.", parent=win)
                                return

                            if not trial_still_active:
                                messagebox.showerror("Trial Expired", "You have already used your 7-day trial on this machine.", parent=win)
                                return

                        if not trial_still_active:
                            # New Trial
                            if not messagebox.askyesno("Activate Trial", "Activate 7-Day Free Trial?", parent=win):
                                return

                        try:
                            # Generate a key for +7 days
                            if trial_still_active:
                                # Logic to use original expiry if needed, or just +7 days from now (simplification for user experience)
                                # But to be correct let's use the calculated one if available
                                if 'expiry_date' in locals():
                                    target_expiry = expiry_date.strftime("%Y-%m-%d")
                                else:
                                    target_expiry = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
                            else:
                                target_expiry = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

                            
                            # Generate key using the Manager (client has access to it)
                            trial_key = LicenseManager.generate_key(hwid_val, target_expiry)
                            
                            # Validate just to be sure
                            valid, v_msg, v_exp = LicenseManager.validate_key(trial_key)
                            if valid:
                                LicenseManager.save_key(trial_key)
                                
                                # Write marker ONLY IF NEW
                                if not trial_still_active:
                                    with open(marker_path, "w") as f:
                                        f.write(f"used_on={datetime.utcnow()}")
                                    
                                messagebox.showinfo("Success", f"Trial Activated/Restored!\nExpires: {v_exp}", parent=win)
                                result_container["key"] = trial_key
                                win.destroy()
                            else:
                                messagebox.showerror("Error", "Failed to generate trial key.", parent=win)
                        except Exception as e:
                            messagebox.showerror("Error", f"Trial activation error: {e}", parent=win)

                    entry_key.bind('<Return>', on_submit)

                    def on_cancel():
                        win.destroy()
                    
                    win.protocol("WM_DELETE_WINDOW", on_cancel)

                    f_btns = tk.Frame(win)
                    f_btns.pack(pady=20)
                    
                    # Trial Button
                    tk.Button(f_btns, text="Trial 7 Days", command=on_trial, bg="#28a745", fg="white", font=("Segoe UI", 9), width=12).pack(side=tk.LEFT, padx=(5, 20))
                    
                    tk.Button(f_btns, text="Activate License", command=on_submit, bg="#007bff", fg="white", font=("Segoe UI", 10, "bold"), width=15).pack(side=tk.LEFT, padx=5)
                    tk.Button(f_btns, text="Exit", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)
                    
                    win.mainloop()
                    return result_container["key"]

                # Prepare Message
                status_msg = "License missing or invalid."
                if status == "expired":
                    status_msg = f"License Expired on {status_info.get('expiration')}."
                
                # Show Dialog
                log_message("Waiting for user input in License Dialog...")
                key = get_license_key_ui(hwid, status_msg)
                
                if not key:
                    log_message("User cancelled license entry. Exiting.")
                    sys.exit(0)
                
                log_message(f"License activated successfully.")
            else:
                log_message(f"✅ License Valid. Expires: {status_info['expiration']}")

        except Exception as e:
            log_message(f"CRITICAL: License check threw exception: {e}")
            import traceback
            log_message(traceback.format_exc())
            # For security, you might want to exit here, strictly enforcing check
            # sys.exit(1) 
            pass # Currently allowing pass-through if check fails due to code error (dev mode safety) but usually should exit
        
        # --- END LICENSE CHECK ---
        
        # Diagnostics: Check CLR
        try:
            log_message("Importing clr (pythonnet)...")
            import clr
            log_message("Adding references...")
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Threading")
            
            log_message("Importing System.Windows.Forms...")
            import System.Windows.Forms
            log_message("✅ .NET dependencies loaded.")
        except Exception as e:
            log_message(f"⚠️ Failed to import clr/System: {e}")
            log_message("Create window might fail if this is required for WinForms.")

        # Configure Playwright for frozen environment
        if getattr(sys, 'frozen', False):
            # Check for browsers in _MEIPASS (onefile mode) or next to executable (onedir mode)
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            
            # Priority: Check for 'browsers' folder next to the .exe (easier for users to update/manage)
            exe_dir = os.path.dirname(sys.executable)
            local_browsers = os.path.join(exe_dir, "browsers")
            
            if os.path.exists(local_browsers):
                 os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browsers
                 log_message(f"📦 Found local browsers folder: {local_browsers}")
            else:
                # Fallback to bundled path (if configured via add-data)
                bundled_browsers = os.path.join(base_path, "browsers")
                if os.path.exists(bundled_browsers):
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers
                    log_message(f"📦 Found bundled browsers: {bundled_browsers}")
                else:
                    log_message(f"⚠️ 'browsers' folder not found in {local_browsers} or {bundled_browsers}")
                    log_message("   If you included browsers, ensure they are in a 'browsers' folder next to the executable.")

        # Enforce Proactor Event Loop for Playwright on Windows
        if sys.platform == 'win32':
            import asyncio
            log_message("🔧 Enforcing WindowsProactorEventLoopPolicy for Playwright support...")
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Check Playwright
        log_message("Checking Playwright...")
        check_and_install_playwright()
        
        # Find Port
        try:
            log_message("Finding free port...")
            server_port = find_free_port()
            log_message(f"✅ Found free port: {server_port}")
        except IOError as e:
            log_message(f"❌ Error finding port: {e}")
            sys.exit(1)
        
        log_message(f"🚀 Starting server on http://127.0.0.1:{server_port}")
        
        # Start server in background
        t = threading.Thread(target=start_server, args=(server_port,), daemon=True)
        t.start()
        
        # Wait for server
        time.sleep(2)
        
        # Launch GUI
        log_message("🖥️  Launching Application Window...")
        try:
            window = webview.create_window(
                'Uni-Video Automation', 
                f'http://127.0.0.1:{server_port}',
                width=1280, # Fallback size
                height=800,
                resizable=True,
                confirm_close=True,
                maximized=True  # Start maximized
            )
            
            # FIX: Add flags to prevent black screen / rendering issues in some environments
            # This disables GPU acceleration which is the most common cause of black screens in WebView2
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu --disable-accelerated-2d-canvas --disable-features=UseSkiaRenderer"
            
            # IMPORTANT: trigger on_closed only when the window is actually closed (via events) 
            # or after start returns.
            # webview.start(func) executes func ON STARTUP. Do not pass on_closed here!
            webview.start(debug=False) # Disable debug for production
            
            log_message("Webview loop finished (Normal exit)")
            on_closed()
            
        except Exception as e:
             log_message(f"CRITICAL ERROR in webview.start: {e}")
             import traceback
             log_message(traceback.format_exc())

    except Exception as e:
        log_message(f"CRITICAL STARTUP ERROR: {e}")
        import traceback
        log_message(traceback.format_exc())
