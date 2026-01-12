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
    '--onefile',                      # Create a single exe file
    '--clean',                        # Clean cache
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
    # Add other hidden imports as needed
]

# Run PyInstaller
print("Building EXE...")
PyInstaller.__main__.run(args)
print("Build complete. Check the 'dist' folder.")
