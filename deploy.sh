#!/bin/bash
set -e

echo "============================================"
echo "  Credit Card Data Extractor — Deploy"
echo "============================================"
echo ""

# Load env if exists
if [ -f .env ]; then
    echo "[1/5] Loading .env..."
    export $(grep -v '^#' .env | xargs)
else
    echo "[1/5] No .env found, using defaults (copy .env.example to .env to customize)"
fi

APP_PORT=${APP_PORT:-80}

# Build all containers
echo ""
echo "[2/5] Building Docker images..."
docker compose build

# Start infrastructure first
echo ""
echo "[3/5] Starting MongoDB, Redis, Ollama..."
docker compose up -d mongo redis ollama

# Wait for Ollama to be ready, then pull models
echo ""
echo "[4/5] Waiting for Ollama and pulling models..."
OLLAMA_MODELS=${OLLAMA_MODELS:-"nomic-embed-text,phi"}

echo "  Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if docker compose exec -T ollama ollama list &>/dev/null; then
        echo "  Ollama is ready!"
        break
    fi
    sleep 2
    echo "  Waiting... ($i/30)"
done

IFS=',' read -ra MODELS <<< "$OLLAMA_MODELS"
for model in "${MODELS[@]}"; do
    model=$(echo "$model" | xargs)  # trim whitespace
    echo "  Pulling model: $model"
    docker compose exec -T ollama ollama pull "$model" || echo "  WARNING: Failed to pull $model"
done

# Start everything
echo ""
echo "[5/5] Starting all services..."
docker compose up -d

echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""
echo "  App:      http://localhost:${APP_PORT}"
echo "  API:      http://localhost:${APP_PORT}/api/health"
echo "  Logs:     docker compose logs -f"
echo "  Stop:     docker compose down"
echo "  Reset:    docker compose down -v  (deletes all data)"
echo ""

# Wait and check health
echo "Checking health..."
sleep 5
if curl -sf "http://localhost:${APP_PORT}/health" > /dev/null 2>&1; then
    echo "✓ Backend is healthy!"
else
    echo "⚠ Backend not responding yet. Check logs: docker compose logs backend"
fi

if curl -sf "http://localhost:${APP_PORT}/" > /dev/null 2>&1; then
    echo "✓ Frontend is serving!"
else
    echo "⚠ Frontend not responding yet. Check logs: docker compose logs frontend nginx"
fi
