import uvicorn
import os
import sys
import webbrowser
import threading
import time
import subprocess

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

def start_server():
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("=" * 50)
    print("  Uni-Video Automation")
    print("=" * 50)
    
    
    # Configure Playwright for frozen environment
    if getattr(sys, 'frozen', False):
        # In frozen mode, browsers are in <sys._MEIPASS>/browsers
        base_path = sys._MEIPASS
        browser_path = os.path.join(base_path, "browsers")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browser_path
        print(f"📦 Running in bundled mode. Browser path set to: {browser_path}")

    # Enforce Proactor Event Loop for Playwright on Windows
    if sys.platform == 'win32':
        import asyncio
        print("🔧 Enforcing WindowsProactorEventLoopPolicy for Playwright support...")
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Check Playwright
    check_and_install_playwright()
    
    print("\n🚀 Starting server on http://127.0.0.1:8000")
    print("   Press Ctrl+C to stop\n")
    
    # Open browser in background
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Start server
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n👋 Stopping server...")
        sys.exit(0)
