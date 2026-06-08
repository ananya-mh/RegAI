#!/bin/bash
set -e

echo "=== RegAI VM Setup ==="
echo ""

# ─── Install Docker ─────────────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
    sudo usermod -aG docker "$USER"
    echo ""
    echo "Docker installed. Log out and back in, then run this script again."
    exit 0
fi

# ─── Configure environment ──────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env

    VM_IP=$(curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H "Metadata-Flavor: Google" 2>/dev/null || echo "")

    if [ -n "$VM_IP" ]; then
        echo "Detected external IP: $VM_IP"
        echo "NEXT_PUBLIC_API_URL=http://${VM_IP}:8000" >> .env
    else
        read -p "Enter VM external IP: " VM_IP
        echo "NEXT_PUBLIC_API_URL=http://${VM_IP}:8000" >> .env
    fi

    echo ""
    echo "Optional: add GEMINI_API_KEY to .env (Ollama works as fallback)"
    echo "  nano .env"
    echo ""
    read -p "Press Enter to continue..."
fi

# ─── Build and start ────────────────────────────────────────────────────────
echo "Building and starting services..."
docker compose -f docker/docker-compose.yml up -d --build

# ─── Wait for services ──────────────────────────────────────────────────────
echo "Waiting for services to start..."
sleep 15

# ─── Run database migrations ────────────────────────────────────────────────
echo "Running database migrations..."
docker compose -f docker/docker-compose.yml exec -T api alembic upgrade head || echo "Migration failed — retry: docker compose -f docker/docker-compose.yml exec api alembic upgrade head"

# ─── Pull Ollama model ──────────────────────────────────────────────────────
echo "Pulling Llama 3 model (~4.7 GB, takes a few minutes)..."
docker compose -f docker/docker-compose.yml exec -T ollama ollama pull llama3:8b || echo "Ollama pull failed — retry: docker compose -f docker/docker-compose.yml exec ollama ollama pull llama3:8b"

# ─── Done ────────────────────────────────────────────────────────────────────
VM_IP=$(curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H "Metadata-Flavor: Google" 2>/dev/null || echo "<VM_IP>")

echo ""
echo "=== Setup complete ==="
echo ""
echo "Frontend:  http://${VM_IP}:3001"
echo "API:       http://${VM_IP}:8000"
echo "API Docs:  http://${VM_IP}:8000/docs"
echo ""
echo "Firewall: make sure GCP allows TCP 3001 and 8000."
