import uvicorn
import threading
import sys
import os
import webview
import time
import socket
from app.main import app

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

# Global variable to store the selected port
SERVER_PORT = 8001

def start_server(port):
    """Starts the FastAPI server in a background thread."""
    # Run uvicorn Programmatically
    # log_level="error" to reduce noise in the console mixed with GUI logs
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

def on_closed():
    """Handler for when the window is closed."""
    print("App window closed. Shutting down...")
    # Give some time for cleanup if needed
    os._exit(0)

if __name__ == "__main__":
    print("Starting Uni-Video GUI PoC...")
    
    # 1. Find a free port
    try:
        SERVER_PORT = find_free_port()
        print(f"✅ Found free port: {SERVER_PORT}")
    except IOError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    # 2. Start the server server in a separate thread
    # Daemon=True means it will die when the main thread dies, 
    # but we also forcefully exit in on_closed to be sure.
    t = threading.Thread(target=start_server, args=(SERVER_PORT,), daemon=True)
    t.start()

    # 3. Wait a bit for the server to be likely up
    # In a production app, we might poll http://127.0.0.1:port/check
    time.sleep(2)

    # 4. Create the window
    # width/height can be adjusted. resizable=True allows standard window behavior.
    window = webview.create_window(
        'Uni-Video Automation', 
        f'http://127.0.0.1:{SERVER_PORT}',
        width=1280,
        height=800,
        resizable=True,
        confirm_close=True # Ask user if they really want to quit
    )

    # 5. Start the GUI loop
    # This must be on the main thread
    webview.start(on_closed, debug=True)
