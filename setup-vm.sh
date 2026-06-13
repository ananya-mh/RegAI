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

    if [ -z "$VM_IP" ]; then
        read -p "Enter VM external IP: " VM_IP
    fi

    echo "Using external IP: $VM_IP"
    sed -i "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${VM_IP}:8000|" .env
    sed -i "s|NEXT_PUBLIC_MCP_SERVER_URL=.*|NEXT_PUBLIC_MCP_SERVER_URL=http://${VM_IP}:3000|" .env
    sed -i "s|NEXTAUTH_URL=.*|NEXTAUTH_URL=http://${VM_IP}:3001|" .env

    echo ""
    echo "Optional: add GEMINI_API_KEY to .env (Ollama works as fallback)"
    echo "  nano .env"
    echo ""
    read -p "Press Enter to continue..."
fi

# ─── Build and start ────────────────────────────────────────────────────────
RUNNING=$(docker compose -f docker/docker-compose.yml ps -q 2>/dev/null | wc -l)
if [ "$RUNNING" -gt 0 ]; then
    echo "Containers already running. Starting any stopped services..."
    docker compose -f docker/docker-compose.yml --env-file .env up -d
else
    echo "Building and starting services (first run)..."
    docker compose -f docker/docker-compose.yml --env-file .env up -d --build
fi

# ─── Wait for services ──────────────────────────────────────────────────────
echo "Waiting for services to start..."
sleep 15

# ─── Run database migrations ────────────────────────────────────────────────
echo "Running database migrations..."
docker compose -f docker/docker-compose.yml --env-file .env exec -T api alembic upgrade head || echo "Migration failed — retry: docker compose -f docker/docker-compose.yml --env-file .env exec api alembic upgrade head"

# ─── Ingest GDPR (skip if already ingested) ────────────────────────────────
FRAMEWORK_COUNT=$(curl -s http://localhost:8000/api/frameworks | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "$FRAMEWORK_COUNT" = "0" ]; then
    echo "Ingesting GDPR regulatory text (downloads from EUR-Lex)..."
    curl -s -X POST "http://localhost:8000/api/frameworks/ingest/gdpr" | head -1 || echo "GDPR ingestion failed — retry: curl -X POST http://localhost:8000/api/frameworks/ingest/gdpr"
else
    echo "Frameworks already ingested ($FRAMEWORK_COUNT found), skipping."
fi

# ─── Pull Ollama model (skip if already pulled) ───────────────────────────
OLLAMA_MODELS=$(docker compose -f docker/docker-compose.yml --env-file .env exec -T ollama ollama list 2>/dev/null || echo "")
if echo "$OLLAMA_MODELS" | grep -q "llama3:8b"; then
    echo "Llama 3 8B already pulled, skipping."
else
    echo "Pulling Llama 3 model (~4.7 GB, takes a few minutes)..."
    docker compose -f docker/docker-compose.yml --env-file .env exec -T ollama ollama pull llama3:8b || echo "Ollama pull failed — retry: docker compose -f docker/docker-compose.yml --env-file .env exec ollama ollama pull llama3:8b"
fi

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
