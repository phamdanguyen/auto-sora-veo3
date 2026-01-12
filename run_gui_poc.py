import uvicorn
import threading
import sys
import os
import webview
import time
from app.main import app

def start_server():
    """Starts the FastAPI server in a background thread."""
    # Run uvicorn Programmatically
    # log_level="error" to reduce noise in the console mixed with GUI logs
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")

def on_closed():
    """Handler for when the window is closed."""
    print("App window closed. Shutting down...")
    # Give some time for cleanup if needed
    os._exit(0)

if __name__ == "__main__":
    print("Starting Uni-Video GUI PoC...")
    
    # Start the server server in a separate thread
    # Daemon=True means it will die when the main thread dies, 
    # but we also forcefully exit in on_closed to be sure.
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Wait a bit for the server to be likely up
    # In a production app, we might poll http://127.0.0.1:8001/health
    time.sleep(2)

    # Create the window
    # width/height can be adjusted. resizable=True allows standard window behavior.
    window = webview.create_window(
        'Uni-Video Automation', 
        'http://127.0.0.1:8001',
        width=1280,
        height=800,
        resizable=True,
        confirm_close=True # Ask user if they really want to quit
    )

    # Start the GUI loop
    # This must be on the main thread
    webview.start(on_closed, debug=True)
