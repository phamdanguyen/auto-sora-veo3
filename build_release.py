import PyInstaller.__main__
import os
import shutil

def build_exe():
    print("🚀 Starting Build Process...")
    
    # 1. Clean previous builds
    print("🧹 Cleaning old builds...")
    for folder in ["build", "dist", "release_pkg"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    
    os.makedirs("release_pkg", exist_ok=True)
        
    # 2. Build KeyGen (OneFile)
    print("\n🔨 Building KeyGen.exe...")
    PyInstaller.__main__.run([
        'scripts/tools/keygen.py', 
        '--name=KeyGen',
        '--onefile',
        '--noconsole',
        '--clean',
        '--workpath=build/keygen',
        '--distpath=dist/keygen'
    ])
    
    # Move KeyGen to release package
    if os.path.exists("dist/keygen/KeyGen.exe"):
        shutil.copy("dist/keygen/KeyGen.exe", "release_pkg/KeyGen.exe")
        print("✅ KeyGen.exe moved to release_pkg/")
    
    # 3. Build Uni-Video (OneDir)
    print("\n🔨 Building Uni-Video Main App...")
    PyInstaller.__main__.run([
        'run_exe.py',
        '--name=Uni-Video',
        '--onedir',
        '--console', 
        '--clean',
        '--workpath=build/univideo',
        '--distpath=dist/univideo',
        '--add-data=app/web/templates;app/web/templates',
        '--add-data=app/web/static;app/web/static',
        '--hidden-import=uvicorn.logging',
        '--hidden-import=uvicorn.loops',
        '--hidden-import=uvicorn.loops.auto',
        '--hidden-import=uvicorn.protocols',
        '--hidden-import=uvicorn.protocols.http',
        '--hidden-import=uvicorn.protocols.http.auto',
        '--hidden-import=uvicorn.lifespan',
        '--hidden-import=uvicorn.lifespan.on',
        '--hidden-import=engineio.async_drivers.aiohttp',
        '--hidden-import=sqlalchemy.sql.default_comparator',
        '--hidden-import=clr',
        '--hidden-import=System',
        '--hidden-import=System.Windows.Forms',
        '--hidden-import=System.Threading',
    ])
    
    # Copy Uni-Video folder to release package
    if os.path.exists("dist/univideo/Uni-Video"):
        shutil.copytree("dist/univideo/Uni-Video", "release_pkg/Uni-Video", dirs_exist_ok=True)
        print("✅ Uni-Video folder moved to release_pkg/")

    print("\n🎉 All Builds Complete!")
    print("Final files are in the 'release_pkg' directory:")
    print("  - release_pkg/KeyGen.exe (For Admin)")
    print("  - release_pkg/Uni-Video/ (Main App Folder)")


if __name__ == "__main__":
    build_exe()
