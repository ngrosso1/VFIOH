#!/bin/bash
# Setup script for VFIOH AI troubleshooting features

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}Setting up VFIOH AI Troubleshooting...${NC}\n"

# Create necessary directories
echo "Creating directories..."
mkdir -p logs
mkdir -p troubleshoot
mkdir -p ai
mkdir -p llm_container

# Create __init__.py files if they don't exist
touch troubleshoot/__init__.py
touch ai/__init__.py

# Set executable permissions on management script
if [ -f "llm_container/manage_llm.sh" ]; then
    chmod +x llm_container/manage_llm.sh
    echo -e "${GREEN}✓${NC} Made manage_llm.sh executable"
fi

# Check for Docker (optional)
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker found"
    
    if docker info &> /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Docker daemon is running"
    else
        echo -e "${RED}⚠${NC} Docker daemon is not running"
        echo "  You'll need to start it to use containerized LLM"
    fi
else
    echo -e "${RED}⚠${NC} Docker not found (optional)"
    echo "  Install Docker to use containerized LLM option"
    echo "  Or use local Ollama installation instead"
fi

# Check for Ollama (optional)
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓${NC} Ollama found"
else
    echo -e "${RED}⚠${NC} Ollama not found (optional)"
    echo "  Install from: https://ollama.com"
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."

check_python_module() {
    python3 -c "import $1" 2>/dev/null && echo -e "${GREEN}✓${NC} $1" || echo -e "${RED}✗${NC} $1 (missing)"
}

check_python_module "requests"
check_python_module "json"
check_python_module "pathlib"

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Install missing dependencies (if any shown above)"
echo "  2. For containerized LLM:"
echo "     cd llm_container"
echo "     ./manage_llm.sh start"
echo "     ./manage_llm.sh pull llama3.1:8b"
echo ""
echo "  3. For local Ollama:"
echo "     ollama serve"
echo "     ollama pull llama3.1:8b"
echo ""
echo "  4. Run VFIOH and select option 6 (AI Troubleshooting)"
echo ""
echo "See AI_TROUBLESHOOTING.md for detailed documentation"