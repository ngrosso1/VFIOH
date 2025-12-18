#!/bin/bash
# Helper script to manage VFIOH LLM container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        echo "Please start Docker service"
        exit 1
    fi
}

start_container() {
    print_status "Starting VFIOH LLM container..."
    
    check_docker
    
    if docker ps | grep -q vfioh-ollama; then
        print_warning "Container is already running"
        return
    fi
    
    docker-compose up -d
    
    print_status "Waiting for service to be ready..."
    sleep 5
    
    if docker ps | grep -q vfioh-ollama; then
        print_success "Container started successfully"
        print_status "Ollama API available at: http://localhost:11434"
    else
        print_error "Container failed to start"
        echo "Check logs with: docker-compose logs"
        exit 1
    fi
}

stop_container() {
    print_status "Stopping VFIOH LLM container..."
    
    docker-compose down
    
    print_success "Container stopped"
}

restart_container() {
    stop_container
    start_container
}

pull_model() {
    local model=${1:-"llama3.1:8b"}
    
    print_status "Pulling model: $model"
    
    if ! docker ps | grep -q vfioh-ollama; then
        print_error "Container is not running"
        echo "Start it first with: $0 start"
        exit 1
    fi
    
    docker exec -it vfioh-ollama ollama pull "$model"
    
    if [ $? -eq 0 ]; then
        print_success "Model pulled successfully"
    else
        print_error "Failed to pull model"
        exit 1
    fi
}

list_models() {
    print_status "Available models:"
    
    if ! docker ps | grep -q vfioh-ollama; then
        print_error "Container is not running"
        echo "Start it first with: $0 start"
        exit 1
    fi
    
    docker exec vfioh-ollama ollama list
}

container_status() {
    print_status "Container status:"
    
    if docker ps | grep -q vfioh-ollama; then
        print_success "Container is RUNNING"
        docker ps | grep vfioh-ollama
        
        echo ""
        print_status "Testing API connection..."
        if curl -s http://localhost:11434/api/tags > /dev/null; then
            print_success "API is accessible"
        else
            print_warning "API is not responding"
        fi
        
    elif docker ps -a | grep -q vfioh-ollama; then
        print_warning "Container exists but is STOPPED"
        echo "Start it with: $0 start"
    else
        print_warning "Container does not exist"
        echo "Create it with: $0 start"
    fi
}

view_logs() {
    if ! docker ps -a | grep -q vfioh-ollama; then
        print_error "Container does not exist"
        exit 1
    fi
    
    print_status "Showing container logs (Ctrl+C to exit)..."
    docker-compose logs -f
}

cleanup() {
    print_warning "This will remove the container AND all downloaded models"
    read -p "Are you sure? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        print_status "Cancelled"
        return
    fi
    
    print_status "Removing container and volumes..."
    docker-compose down -v
    
    print_success "Cleanup complete"
}

show_help() {
    cat << EOF
VFIOH LLM Container Management

Usage: $0 <command> [options]

Commands:
    start           Start the Ollama container
    stop            Stop the container
    restart         Restart the container
    status          Show container status
    pull [model]    Pull a model (default: llama3.1:8b)
    list            List available models
    logs            View container logs
    cleanup         Remove container and all data
    help            Show this help message

Examples:
    $0 start                    # Start container
    $0 pull llama3.1:8b        # Pull recommended model
    $0 pull llama3.2:3b        # Pull smaller/faster model
    $0 status                   # Check if running
    $0 logs                     # View logs

Recommended models:
    llama3.1:8b     - Balanced (8GB RAM, ~4.7GB download)
    llama3.2:3b     - Faster (4GB RAM, ~2GB download)
    mixtral:8x7b    - Most accurate (16GB RAM, ~26GB download)
EOF
}

# Main script logic
case "${1:-help}" in
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    status)
        container_status
        ;;
    pull)
        pull_model "$2"
        ;;
    list)
        list_models
        ;;
    logs)
        view_logs
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac