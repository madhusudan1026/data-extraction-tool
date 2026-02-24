#!/bin/bash
set -e

# ============================================
# SSL Setup with Let's Encrypt + Certbot
# ============================================
# Run AFTER deploy.sh, once your domain points to this server
#
# Usage: ./setup-ssl.sh yourdomain.com

DOMAIN=${1:-$DOMAIN}

if [ -z "$DOMAIN" ]; then
    echo "Usage: ./setup-ssl.sh yourdomain.com"
    echo "Or set DOMAIN in .env"
    exit 1
fi

echo "Setting up SSL for: $DOMAIN"
echo ""

# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    echo "Installing Certbot..."
    sudo apt-get update
    sudo apt-get install -y certbot
fi

# Stop nginx temporarily for standalone cert
echo "Stopping nginx for certificate issuance..."
docker compose stop nginx

# Get certificate
echo "Requesting certificate from Let's Encrypt..."
sudo certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN"

# Create SSL nginx config
echo "Creating SSL nginx config..."
mkdir -p nginx

cat > nginx/default.conf << NGINXEOF
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:80;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /health {
        proxy_pass http://backend;
    }

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINXEOF

# Update docker-compose to mount SSL certs
if ! grep -q "letsencrypt" docker-compose.yml; then
    echo ""
    echo "NOTE: Add these volume mounts to the nginx service in docker-compose.yml:"
    echo ""
    echo "    volumes:"
    echo "      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro"
    echo "      - /etc/letsencrypt:/etc/letsencrypt:ro"
    echo "    ports:"
    echo "      - \"80:80\""
    echo "      - \"443:443\""
fi

# Restart nginx
echo ""
echo "Restarting nginx with SSL..."
docker compose up -d nginx

echo ""
echo "============================================"
echo "  SSL Setup Complete!"
echo "============================================"
echo "  https://$DOMAIN"
echo ""
echo "  Auto-renewal: sudo certbot renew --pre-hook 'docker compose stop nginx' --post-hook 'docker compose start nginx'"
echo ""
