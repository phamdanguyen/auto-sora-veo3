import PyInstaller.__main__
import os
import shutil

# Clean up previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

# Define build arguments
args = [
    'run_exe.py',                     # Script to run
    '--name=UniVideoAutomation',      # Name of the exe
    '--onedir',                       # Create a directory (better for bundling browsers)
    '--clean',                        # Clean cache
    '--noupx',                        # Disable UPX compression to avoid dll errors
    '--add-data=app/web/templates;app/web/templates', # Include templates
    # '--add-data=app/web/static;app/web/static',     # Include static (uncomment if static folder exists)
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols',
    '--hidden-import=uvicorn.protocols.http',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.lifespan',
    '--hidden-import=uvicorn.lifespan.on',
    '--hidden-import=sqlalchemy.sql.default_comparator',
    '--hidden-import=webview',
    '--hidden-import=clr',
    '--hidden-import=System',
    '--hidden-import=System.Windows.Forms',
    '--hidden-import=System.Collections',
    '--hidden-import=System.Threading',
    '--hidden-import=System.Drawing',
    '--hidden-import=pythonnet',
    # Add other hidden imports as needed
]

# Run PyInstaller
print("Building EXE...")
PyInstaller.__main__.run(args)
print("Build complete. Checking for browsers...")

# --- Post-Build: Copy Browsers ---
# Try to find Playwright browsers in standard location
user_profile = os.environ.get("USERPROFILE")
playwright_loc = os.path.join(user_profile, "AppData", "Local", "ms-playwright")

target_dir = os.path.join("dist", "UniVideoAutomation", "browsers")

if os.path.exists(playwright_loc):
    print(f"📥 Found Playwright browsers at: {playwright_loc}")
    print(f"   Copying to dist folder: {target_dir} (This may take a while...)")
    try:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(playwright_loc, target_dir)
        print("✅ Browsers copied successfully!")
    except Exception as e:
        print(f"❌ Failed to copy browsers: {e}")
else:
    print(f"⚠️ Playwright browsers not found at default location: {playwright_loc}")
    print("   Please manually copy your 'ms-playwright' folder to 'dist/UniVideoAutomation/browsers' if needed.")

print("\n🎉 Distribution Ready in 'dist/UniVideoAutomation'")
print("Build complete. Check the 'dist' folder.")
