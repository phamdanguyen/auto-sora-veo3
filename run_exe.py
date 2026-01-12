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
    # Run uvicorn Programmatically
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

def on_closed():
    """Handler for when the window is closed."""
    print("App window closed. Shutting down...")
    os._exit(0)

if __name__ == "__main__":
    print("=" * 50)
    print("  Uni-Video Automation (GUI Mode)")
    print("=" * 50)
    
    # Configure Playwright for frozen environment
    if getattr(sys, 'frozen', False):
        # Check for browsers in _MEIPASS (onefile mode) or next to executable (onedir mode)
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        
        # Priority: Check for 'browsers' folder next to the .exe (easier for users to update/manage)
        exe_dir = os.path.dirname(sys.executable)
        local_browsers = os.path.join(exe_dir, "browsers")
        
        if os.path.exists(local_browsers):
             os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browsers
             print(f"📦 Found local browsers folder: {local_browsers}")
        else:
            # Fallback to bundled path (if configured via add-data)
            bundled_browsers = os.path.join(base_path, "browsers")
            if os.path.exists(bundled_browsers):
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers
                print(f"📦 Found bundled browsers: {bundled_browsers}")
            else:
                print(f"⚠️ 'browsers' folder not found in {local_browsers} or {bundled_browsers}")
                print("   If you included browsers, ensure they are in a 'browsers' folder next to the executable.")

    # Enforce Proactor Event Loop for Playwright on Windows
    if sys.platform == 'win32':
        import asyncio
        print("🔧 Enforcing WindowsProactorEventLoopPolicy for Playwright support...")
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Check Playwright
    check_and_install_playwright()
    
    # Find Port
    try:
        server_port = find_free_port()
        print(f"✅ Found free port: {server_port}")
    except IOError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    print(f"\n🚀 Starting server on http://127.0.0.1:{server_port}")
    
    # Start server in background
    t = threading.Thread(target=start_server, args=(server_port,), daemon=True)
    t.start()
    
    # Wait for server
    time.sleep(2)
    
    # Launch GUI
    print("🖥️  Launching Application Window...")
    window = webview.create_window(
        'Uni-Video Automation', 
        f'http://127.0.0.1:{server_port}',
        width=1280,
        height=800,
        resizable=True,
        confirm_close=True
    )
    
    webview.start(on_closed, debug=False)
