import PyInstaller.__main__
import os
import shutil
import sys

def build_exe():
    print("🚀 Starting Build Process...")
    
    # Platform specific settings
    is_windows = sys.platform == 'win32'
    separator = ';' if is_windows else ':'
    exe_ext = '.exe' if is_windows else ''
    
    # 1. Clean previous builds
    print("🧹 Cleaning old builds...")
    for folder in ["build", "dist", "release_pkg"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    
    os.makedirs("release_pkg", exist_ok=True)
        
    # 2. Build KeyGen (OneFile)
    print(f"\n🔨 Building KeyGen{exe_ext}...")
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
    src_keygen = f"dist/keygen/KeyGen{exe_ext}"
    dst_keygen = f"release_pkg/KeyGen{exe_ext}"
    if os.path.exists(src_keygen):
        shutil.copy(src_keygen, dst_keygen)
        print(f"✅ KeyGen{exe_ext} moved to release_pkg/")
    else:
        print(f"⚠️ Warning: {src_keygen} not found.")
    
    # 3. Build Uni-Video (OneDir)
    print("\n🔨 Building Uni-Video Main App...")
    
    uni_video_args = [
        'run_exe.py',
        '--name=Uni-Video',
        '--onedir',
        '--console', 
        '--clean',
        '--workpath=build/univideo',
        '--distpath=dist/univideo',
        f'--add-data=app/web/templates{separator}app/web/templates',
        f'--add-data=app/web/static{separator}app/web/static',
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
        '--hidden-import=webview',
        '--hidden-import=webview.platforms.gtk', # For Linux
        '--hidden-import=dependency_injector.errors',
        '--hidden-import=dependency_injector.containers',
        '--hidden-import=dependency_injector.providers',
        '--hidden-import=dependency_injector.wiring',
    ]

    # Add Windows-specific imports only on Windows
    if is_windows:
        uni_video_args.extend([
            '--hidden-import=clr',
            '--hidden-import=System',
            '--hidden-import=System.Windows.Forms',
            '--hidden-import=System.Threading',
            '--hidden-import=webview.platforms.winforms',
        ])

    PyInstaller.__main__.run(uni_video_args)
    
    # Copy Uni-Video folder to release package
    build_output_dir = "dist/univideo/Uni-Video"
    release_dir = "release_pkg/Uni-Video"
    
    if os.path.exists(build_output_dir):
        # 4. Copy Playwright Browsers
        print("\n📦 Copying Playwright Browsers (for One-Click capability)...")
        if is_windows:
            user_profile = os.environ.get("USERPROFILE")
            playwright_src = os.path.join(user_profile, "AppData", "Local", "ms-playwright")
        else:
            # Linux default
            playwright_src = os.path.expanduser("~/.cache/ms-playwright")
            
        browsers_dst = os.path.join(build_output_dir, "browsers")
        
        if os.path.exists(playwright_src):
            print(f"   Source: {playwright_src}")
            print(f"   Dest: {browsers_dst}")
            if os.path.exists(browsers_dst):
                shutil.rmtree(browsers_dst)
            try:
                shutil.copytree(playwright_src, browsers_dst)
                print("   ✅ Browsers copied successfully!")
            except Exception as e:
                print(f"   ❌ Failed to copy browsers: {e}")
        else:
            print(f"   ⚠️ Playwright browsers not found at: {playwright_src}")
            print("   You may need to run 'playwright install' first or copy them manually.")

        # Move to release_pkg
        if os.path.exists(release_dir):
            shutil.rmtree(release_dir)
        shutil.copytree(build_output_dir, release_dir, dirs_exist_ok=True)
        print("✅ Uni-Video folder moved to release_pkg/")

    print("\n🎉 All Builds Complete!")
    print("Final files are in the 'release_pkg' directory:")
    print(f"  - {dst_keygen} (For Admin)")
    print("  - release_pkg/Uni-Video/ (Main App Folder)")


if __name__ == "__main__":
    build_exe()
