#!/bin/bash
# Clean ALL build artifacts from PyInstaller and AppImage creation

echo "🧹 Cleaning up build artifacts..."

# Remove PyInstaller artifacts
rm -rf build/ dist/ *.spec

# Remove AppImage build directory
rm -rf AppDir/ squashfs-root/

# Remove Python cache files
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
find . -type f -name "*.pyo" -delete 2>/dev/null
find . -type f -name "*.pyd" -delete 2>/dev/null
find . -type f -name "*.py.class" -delete 2>/dev/null

# Remove temporary directories from failed scripts
rm -rf _build/ _temp/ venv/ .venv/

# Remove test files that might have been created
rm -f test_imports.py mytui*.py MyTUIApp_wrapper.py

# Remove downloaded appimagetool (optional - keep if you want)
# rm -f appimagetool* AppRun

# Remove any leftover .log files
rm -f *.log

rm appimagetool-x86_64.AppImag*
rm MyTUIApp.AppImage
rm -rf venv
rm -rf dist
rm -rf build
rm -rf AppDir

echo "✅ Cleanup complete!"
echo ""
echo "Current directory contents:"
ls -la