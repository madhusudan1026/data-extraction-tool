#!/bin/bash
set -e

echo "============================================"
echo "  Oracle Cloud ARM VM — Full Setup"
echo "  Credit Card Data Extractor"
echo "============================================"
echo ""
echo "Architecture: $(uname -m)"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo ""

# ---- 1. System packages ----
echo "[1/7] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq unzip curl git iptables-persistent < /dev/null

# ---- 2. Docker ----
if command -v docker &> /dev/null; then
    echo "[2/7] Docker already installed: $(docker --version)"
else
    echo "[2/7] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

# Ensure docker compose plugin is available
if ! docker compose version &> /dev/null; then
    echo "  Installing Docker Compose plugin..."
    sudo apt-get install -y -qq docker-compose-plugin < /dev/null
fi

echo "  Docker: $(docker --version)"
echo "  Compose: $(docker compose version)"

# ---- 3. Firewall ----
echo ""
echo "[3/7] Opening firewall ports (80, 443)..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true

# ---- 4. Project setup ----
echo ""
echo "[4/7] Setting up project..."
PROJECT_DIR="$HOME/app"

if [ -f "$HOME/data-extraction-tool-full.zip" ] && [ ! -d "$PROJECT_DIR/backend-python" ]; then
    echo "  Extracting project zip..."
    mkdir -p "$PROJECT_DIR"
    unzip -o "$HOME/data-extraction-tool-full.zip" -d "$PROJECT_DIR"
elif [ -d "$PROJECT_DIR/backend-python" ]; then
    echo "  Project already exists at $PROJECT_DIR"
else
    echo "  ERROR: No project zip found at ~/data-extraction-tool-full.zip"
    echo "  Upload it with: scp data-extraction-tool-full.zip ubuntu@<IP>:~"
    exit 1
fi

cd "$PROJECT_DIR"

# ---- 5. Configure ----
echo ""
echo "[5/7] Configuring..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from template"
fi

# Ensure deploy script is executable
chmod +x deploy.sh setup-ssl.sh 2>/dev/null || true

# ---- 6. Build and deploy ----
echo ""
echo "[6/7] Building Docker images (this takes 5-10 minutes on ARM)..."

# Need to run docker commands - if current user isn't in docker group yet,
# use sudo for this session
if ! docker info &>/dev/null 2>&1; then
    echo "  Note: Running docker with sudo (re-login for group changes to take effect)"
    DOCKER_CMD="sudo docker compose"
else
    DOCKER_CMD="docker compose"
fi

$DOCKER_CMD build

echo ""
echo "  Starting infrastructure..."
$DOCKER_CMD up -d mongo redis ollama

echo ""
echo "  Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if $DOCKER_CMD exec -T ollama ollama list &>/dev/null; then
        echo "  Ollama is ready!"
        break
    fi
    sleep 3
    echo "  Waiting... ($i/30)"
done

echo ""
echo "  Pulling LLM models (this takes 5-10 minutes)..."
$DOCKER_CMD exec -T ollama ollama pull nomic-embed-text || echo "  WARNING: Failed to pull nomic-embed-text"
$DOCKER_CMD exec -T ollama ollama pull llama3.2 || echo "  WARNING: Failed to pull llama3.2"

echo ""
echo "  Starting all services..."
$DOCKER_CMD up -d

# ---- 7. Keep-alive cron ----
echo ""
echo "[7/7] Setting up keep-alive cron..."
(crontab -l 2>/dev/null | grep -v "health" ; echo "*/5 * * * * curl -sf http://localhost/health > /dev/null 2>&1") | crontab -

# ---- Done ----
echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""

# Get public IP
PUBLIC_IP=$(curl -sf http://ifconfig.me 2>/dev/null || echo "<your-vm-ip>")

echo "  App:     http://$PUBLIC_IP"
echo "  API:     http://$PUBLIC_IP/api/health"
echo ""
echo "  Logs:    cd ~/app && docker compose logs -f"
echo "  Stop:    cd ~/app && docker compose down"
echo "  Restart: cd ~/app && docker compose up -d"
echo ""

# Health check
sleep 8
echo "Checking health..."
if curl -sf "http://localhost/health" > /dev/null 2>&1; then
    echo "✓ Backend is healthy!"
else
    echo "⚠ Backend starting up... check: docker compose logs -f backend"
fi

if curl -sf "http://localhost/" > /dev/null 2>&1; then
    echo "✓ Frontend is serving!"
else
    echo "⚠ Frontend starting up... check: docker compose logs -f nginx"
fi

echo ""
echo "NOTE: If this is your first login, run 'newgrp docker' or re-login"
echo "      so you can use docker without sudo."
