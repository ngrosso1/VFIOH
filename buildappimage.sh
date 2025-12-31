#!/bin/bash
# build_fucking_appimage.sh
set -e

# Clean everything
rm -rf build dist AppDir MyTUIApp*.AppImage
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Get appimagetool in current directory
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# Build with PyInstaller
pyinstaller --onefile \
    --name=MyTUIApp \
    --add-data="ai:ai" \
    --add-data="troubleshoot:troubleshoot" \
    --add-data="llm_container:llm_container" \
    --add-data="logs:logs" \
    --add-data="*.py:." \
    --add-data="*.sh:." \
    --hidden-import=libvirt \
    --hidden-import=tkinter \
    --clean \
    main.py

# Create AppDir HERE (not in _build)
mkdir -p AppDir/usr/{bin,lib,share/MyTUIApp}

# Copy executable
cp dist/MyTUIApp AppDir/usr/bin/

# Copy project files
cp -r ai troubleshoot llm_container logs AppDir/usr/share/MyTUIApp/
cp *.py *.sh AppDir/usr/share/MyTUIApp/ 2>/dev/null || true

# Try to copy libvirt
cp -r /usr/lib/python3*/site-packages/libvirt* AppDir/usr/lib/ 2>/dev/null || true
cp -r /usr/local/lib/python3*/site-packages/libvirt* AppDir/usr/lib/ 2>/dev/null || true

# Create the fucking desktop file
echo '[Desktop Entry]
Name=MyTUIApp
Exec=AppRun
Type=Application
Terminal=true' > AppDir/MyTUIApp.desktop

# Create AppRun
echo '#!/bin/bash
cd "$(dirname "$0")/usr/share/MyTUIApp"
export PYTHONPATH="$(dirname "$0")/usr/lib:$PWD"
exec ../bin/MyTUIApp' > AppDir/AppRun
chmod +x AppDir/AppRun

# Build the fucking AppImage
./appimagetool-x86_64.AppImage AppDir MyTUIApp.AppImage

# Clean up
rm -rf AppDir build

echo "✅ Done: MyTUIApp.AppImage"
echo "Run: ./MyTUIApp.AppImage"