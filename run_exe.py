import uvicorn
import os
import sys
import threading
import time
import subprocess
import socket
import webview
from app.main import app

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
            webview.start(debug=True) # Enable debug for Right Click > Inspect 
            
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
