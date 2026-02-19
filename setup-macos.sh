# macOS Complete Setup Guide for MacBook Pro

## 🍎 Prerequisites Installation for macOS

### Step 1: Install Homebrew (Package Manager)

Homebrew is the easiest way to install development tools on macOS.

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Follow the "Next steps" instructions shown after installation
# Usually you need to add Homebrew to your PATH
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Verify installation
brew --version
```

### Step 2: Install Node.js and npm

**Option A: Using Homebrew (Recommended)**

```bash
# Install Node.js (includes npm)
brew install node

# Verify installation
node --version   # Should show v20.x.x or v18.x.x
npm --version    # Should show v10.x.x or v9.x.x
```

**Option B: Using Official Installer**

1. Go to https://nodejs.org/
2. Download the macOS installer (LTS version recommended)
3. Run the installer
4. Verify:
```bash
node --version
npm --version
```

**Option C: Using nvm (Node Version Manager)**

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Close and reopen terminal, then:
nvm install 20
nvm use 20
nvm alias default 20

# Verify
node --version
npm --version
```

### Step 3: Install Git

```bash
# Check if Git is already installed (comes with Xcode Command Line Tools)
git --version

# If not installed:
brew install git

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Step 4: Install Docker Desktop

**Option A: Using Homebrew**

```bash
# Install Docker Desktop
brew install --cask docker

# Start Docker Desktop from Applications folder
# Wait for Docker to start (whale icon in menu bar)

# Verify
docker --version
docker-compose --version
```

**Option B: Manual Installation**

1. Download from https://www.docker.com/products/docker-desktop
2. Install Docker.dmg
3. Start Docker Desktop from Applications
4. Verify in terminal:
```bash
docker --version
docker-compose --version
```

### Step 5: Install Visual Studio Code

**Option A: Using Homebrew**

```bash
brew install --cask visual-studio-code

# Verify
code --version
```

**Option B: Manual Installation**

1. Download from https://code.visualstudio.com/
2. Move to Applications folder
3. Add to PATH:
```bash
# Open VS Code
# Press Cmd+Shift+P
# Type "shell command"
# Select "Shell Command: Install 'code' command in PATH"
```

### Step 6: Verify Everything is Installed

```bash
# Run this verification script
cat << 'EOF' > verify-install.sh
#!/bin/bash

echo "🔍 Verifying installations..."

command -v node >/dev/null 2>&1 && echo "✅ Node.js: $(node --version)" || echo "❌ Node.js not found"
command -v npm >/dev/null 2>&1 && echo "✅ npm: $(npm --version)" || echo "❌ npm not found"
command -v git >/dev/null 2>&1 && echo "✅ Git: $(git --version)" || echo "❌ Git not found"
command -v docker >/dev/null 2>&1 && echo "✅ Docker: $(docker --version)" || echo "❌ Docker not found"
command -v code >/dev/null 2>&1 && echo "✅ VS Code: $(code --version | head -n1)" || echo "❌ VS Code not found"
command -v brew >/dev/null 2>&1 && echo "✅ Homebrew: $(brew --version | head -n1)" || echo "⚠️  Homebrew not found (optional)"

echo ""
echo "🎯 All required tools installed!" 
EOF

chmod +x verify-install.sh
./verify-install.sh
```

## 🚀 macOS-Optimized Setup Script

Save this as `setup-macos.sh`:

```bash
#!/bin/bash

# Data Extraction Tool - macOS Setup Script
set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Data Extraction Tool - macOS Setup${NC}"
echo ""

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found!${NC}"
    echo "Please install Node.js first:"
    echo "  brew install node"
    echo "Or download from: https://nodejs.org/"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠️  Docker not found!${NC}"
    echo "Please install Docker Desktop:"
    echo "  brew install --cask docker"
    echo "Or download from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

echo -e "${GREEN}✅ All prerequisites installed${NC}"
echo ""

# Project setup
PROJECT_NAME="data-extraction-tool"
PROJECT_ROOT="$HOME/Projects/$PROJECT_NAME"

# Create Projects directory if it doesn't exist
mkdir -p "$HOME/Projects"

echo -e "${BLUE}Creating project at: $PROJECT_ROOT${NC}"
mkdir -p "$PROJECT_ROOT"
cd "$PROJECT_ROOT"

# Create directory structure
echo -e "${BLUE}Creating directory structure...${NC}"
mkdir -p backend/src/{config,models,services,routes,middleware,utils,scripts,tests/{unit,integration}}
mkdir -p frontend/src/{components,services,hooks,utils}
mkdir -p .vscode

# Create root package.json
echo -e "${BLUE}Creating package.json files...${NC}"
cat > package.json << 'EOF'
{
  "name": "data-extraction-tool",
  "version": "1.0.0",
  "description": "Intelligent data extraction tool with MongoDB and LLM",
  "private": true,
  "workspaces": ["backend", "frontend"],
  "scripts": {
    "install-all": "npm install && cd backend && npm install && cd ../frontend && npm install",
    "dev:backend": "cd backend && npm run dev",
    "dev:frontend": "cd frontend && npm run dev",
    "dev": "concurrently \"npm run dev:backend\" \"npm run dev:frontend\"",
    "docker:up": "docker-compose up -d",
    "docker:down": "docker-compose down",
    "docker:logs": "docker-compose logs -f",
    "models": "docker exec -it extraction-ollama ollama pull llama3.2",
    "test": "npm run test --workspaces"
  },
  "devDependencies": {
    "concurrently": "^8.2.2"
  }
}
EOF

# Create backend package.json
cat > backend/package.json << 'EOF'
{
  "name": "extraction-backend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "nodemon src/server.js",
    "start": "node src/server.js",
    "test": "jest --coverage",
    "migrate": "node src/scripts/migrate.js",
    "seed": "node src/scripts/seed.js",
    "lint": "eslint src/"
  },
  "dependencies": {
    "express": "^4.18.2",
    "mongoose": "^8.0.3",
    "redis": "^4.6.11",
    "axios": "^1.6.2",
    "pdf-parse": "^1.1.1",
    "pdfjs-dist": "^3.11.174",
    "cheerio": "^1.0.0-rc.12",
    "puppeteer": "^21.6.1",
    "bull": "^4.12.0",
    "joi": "^17.11.0",
    "dotenv": "^16.3.1",
    "winston": "^3.11.0",
    "helmet": "^7.1.0",
    "cors": "^2.8.5",
    "express-rate-limit": "^7.1.5",
    "multer": "^1.4.5-lts.1",
    "uuid": "^9.0.1",
    "p-limit": "^5.0.0"
  },
  "devDependencies": {
    "nodemon": "^3.0.2",
    "jest": "^29.7.0",
    "supertest": "^6.3.3",
    "eslint": "^8.55.0"
  }
}
EOF

# Create frontend package.json
cat > frontend/package.json << 'EOF'
{
  "name": "extraction-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.6.2",
    "lucide-react": "^0.294.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.1",
    "vite": "^5.0.7",
    "tailwindcss": "^3.3.6",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.32"
  }
}
EOF

# Create .env files
echo -e "${BLUE}Creating environment files...${NC}"
cat > backend/.env << 'EOF'
MONGODB_URI=mongodb://admin:admin123@localhost:27017/extraction_db?authSource=admin
REDIS_URL=redis://localhost:6379
OLLAMA_URL=http://localhost:11434/api/generate
DEFAULT_MODEL=llama3.2
DEFAULT_TEMPERATURE=0.1
NODE_ENV=development
PORT=3000
CORS_ORIGIN=http://localhost:5173
BATCH_CONCURRENCY=3
LOG_LEVEL=info
EOF

cp backend/.env backend/.env.example

# Create .gitignore
cat > .gitignore << 'EOF'
node_modules/
.env
.env.local
dist/
build/
*.log
.DS_Store
.vscode/settings.json
mongodb_data/
redis_data/
ollama_data/
EOF

# Create docker-compose.yml (macOS optimized)
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  mongodb:
    image: mongo:7.0
    container_name: extraction-mongodb
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: admin123
      MONGO_INITDB_DATABASE: extraction_db
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - extraction-network

  redis:
    image: redis:7-alpine
    container_name: extraction-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - extraction-network

  ollama:
    image: ollama/ollama:latest
    container_name: extraction-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - extraction-network

  mongo-express:
    image: mongo-express:latest
    container_name: extraction-mongo-express
    ports:
      - "8081:8081"
    environment:
      ME_CONFIG_MONGODB_ADMINUSERNAME: admin
      ME_CONFIG_MONGODB_ADMINPASSWORD: admin123
      ME_CONFIG_MONGODB_URL: mongodb://admin:admin123@mongodb:27017/
      ME_CONFIG_BASICAUTH_USERNAME: admin
      ME_CONFIG_BASICAUTH_PASSWORD: admin
    depends_on:
      - mongodb
    networks:
      - extraction-network

volumes:
  mongodb_data:
  redis_data:
  ollama_data:

networks:
  extraction-network:
    driver: bridge
EOF

# Create Makefile (macOS compatible)
cat > Makefile << 'EOF'
.PHONY: help install start stop clean models logs

help:
	@echo "Available commands:"
	@echo "  make install      - Install all dependencies"
	@echo "  make start        - Start Docker services"
	@echo "  make stop         - Stop Docker services"
	@echo "  make models       - Download LLM models"
	@echo "  make logs         - Show Docker logs"

install:
	npm install
	cd backend && npm install
	cd frontend && npm install

start:
	docker-compose up -d
	@echo ""
	@echo "✅ Services started:"
	@echo "  - Frontend: http://localhost:5173"
	@echo "  - Backend: http://localhost:3000"
	@echo "  - Mongo Express: http://localhost:8081"

stop:
	docker-compose down

clean:
	docker-compose down -v
	rm -rf node_modules backend/node_modules frontend/node_modules

models:
	docker exec -it extraction-ollama ollama pull llama3.2
	@echo "✅ Models downloaded"

logs:
	docker-compose logs -f
EOF

# Create VS Code settings
mkdir -p .vscode
cat > .vscode/settings.json << 'EOF'
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "files.exclude": {
    "**/node_modules": true,
    "**/.git": true,
    "**/dist": true
  }
}
EOF

cat > .vscode/extensions.json << 'EOF'
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "ms-azuretools.vscode-docker",
    "mongodb.mongodb-vscode",
    "saoudrizwan.claude-dev"
  ]
}
EOF

# Create README
cat > README.md << 'EOF'
# Data Extraction Tool

## Quick Start (macOS)

```bash
# Install dependencies
make install

# Start services
make start

# Download LLM models
make models

# Open in VS Code
code .
```

## Next Steps

1. Copy implementation files from Claude artifacts
2. Run `npm run dev` to start development
3. Access http://localhost:5173
EOF

# Create NEXT_STEPS.md
cat > NEXT_STEPS.md << 'EOF'
# Next Steps

## 1. Copy Implementation Files

Copy code from Claude artifacts into these files:

### Core Files (Create these first):
- backend/src/config/database.js
- backend/src/config/redis.js
- backend/src/utils/logger.js
- backend/src/middleware/errorHandler.js
- backend/src/middleware/rateLimit.js
- backend/src/server.js

### Models:
- backend/src/models/ExtractedData.js
- backend/src/models/ExtractionJob.js
- backend/src/models/Comparison.js
- backend/src/models/CardTemplate.js

### Services:
- backend/src/services/extractionService.js
- backend/src/services/llmService.js
- backend/src/services/pdfService.js
- backend/src/services/webScraperService.js
- backend/src/services/validationService.js
- backend/src/services/batchService.js
- backend/src/services/comparisonService.js

### Routes:
- backend/src/routes/extraction.js
- backend/src/routes/batch.js
- backend/src/routes/comparison.js
- backend/src/routes/schema.js

## 2. Install & Run

```bash
make install
make start
make models
code .
npm run dev
```
EOF

echo ""
echo -e "${GREEN}✅ Project structure created!${NC}"
echo ""
echo -e "${YELLOW}Project location:${NC} $PROJECT_ROOT"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. cd $PROJECT_ROOT"
echo "2. Read NEXT_STEPS.md"
echo "3. Copy code from Claude artifacts"
echo "4. Run: make install"
echo "5. Run: make start"
echo "6. Run: make models"
echo "7. Run: code ."
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
EOF

chmod +x setup-macos.sh
```

## 🎯 Quick Start for macOS

### Complete Setup (Copy-Paste Friendly)

```bash
# 1. Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Add Homebrew to PATH (for Apple Silicon Macs)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# 3. Install all prerequisites
brew install node
brew install git
brew install --cask docker
brew install --cask visual-studio-code

# 4. Start Docker Desktop
open -a Docker

# Wait for Docker to start (check menu bar for whale icon)
# Then verify:
docker --version

# 5. Create and run setup script
cat > setup-macos.sh << 'SCRIPT'
# [Paste the setup-macos.sh script content from above]
SCRIPT

chmod +x setup-macos.sh
./setup-macos.sh

# 6. Navigate to project
cd ~/Projects/data-extraction-tool

# 7. Install dependencies
make install

# 8. Start Docker services
make start

# 9. Download LLM models (takes 5-10 minutes)
make models

# 10. Open in VS Code
code .
```

## 🔧 macOS-Specific Troubleshooting

### Issue: "xcrun: error: invalid active developer path"

This means Xcode Command Line Tools aren't installed.

**Fix:**
```bash
xcode-select --install
```

### Issue: Docker Desktop won't start

**Fix:**
```bash
# Completely remove and reinstall
brew uninstall --cask docker
brew install --cask docker

# Or download fresh installer from docker.com
```

### Issue: Port 27017 already in use

**Fix:**
```bash
# Check what's using the port
lsof -i :27017

# If it's MongoDB, stop it
brew services stop mongodb-community

# Or kill the process
kill -9 <PID>
```

### Issue: Permission denied errors

**Fix:**
```bash
# Fix npm permissions (macOS recommended way)
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zprofile
source ~/.zprofile
```

### Issue: "command not found" after installing with brew

**Fix:**
```bash
# Restart terminal or source profile
source ~/.zprofile

# Or add Homebrew to PATH
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
```

### Issue: Docker containers can't connect to each other

**Fix:**
```bash
# Reset Docker Desktop
# Click Docker icon in menu bar → Preferences → Reset → Reset to factory defaults
```

## 📱 macOS File Locations

- **Project**: `~/Projects/data-extraction-tool`
- **Homebrew**: `/opt/homebrew` (Apple Silicon) or `/usr/local` (Intel)
- **Node modules**: `~/.npm-global`
- **VS Code**: `/Applications/Visual Studio Code.app`
- **Docker Desktop**: `/Applications/Docker.app`

## ⌨️ macOS Keyboard Shortcuts

### Terminal
- `Cmd + N` - New terminal window
- `Cmd + T` - New terminal tab
- `Cmd + K` - Clear terminal

### VS Code
- `Cmd + Shift + P` - Command palette
- `Cmd + ` ` - Toggle terminal
- `Cmd + P` - Quick file open
- `Cmd + Shift + F` - Search in files

## 🍎 Apple Silicon (M1/M2/M3) Notes

Everything works on Apple Silicon, but note:

1. **Docker**: Use the Apple Silicon version
2. **Ollama**: Runs natively on Apple Silicon (very fast!)
3. **Node.js**: Install ARM64 version via Homebrew
4. **Path**: Use `/opt/homebrew` instead of `/usr/local`

## ✅ Final Verification

Run this to verify everything:

```bash
# Create verification script
cat > verify.sh << 'EOF'
#!/bin/bash
echo "🔍 Verifying macOS setup..."
echo ""
command -v node && echo "✅ Node: $(node --version)" || echo "❌ Node.js not found"
command -v npm && echo "✅ npm: $(npm --version)" || echo "❌ npm not found"
command -v git && echo "✅ Git: $(git --version | head -n1)" || echo "❌ Git not found"
command -v docker && echo "✅ Docker: $(docker --version)" || echo "❌ Docker not found"
command -v code && echo "✅ VS Code installed" || echo "❌ VS Code not found"
docker ps &>/dev/null && echo "✅ Docker running" || echo "⚠️  Docker not running"
EOF

chmod +x verify.sh
./verify.sh
```

Expected output:
```
✅ Node: v20.x.x
✅ npm: v10.x.x
✅ Git: git version 2.x.x
✅ Docker: Docker version 24.x.x
✅ VS Code installed
✅ Docker running
```

## 🚀 You're Ready!

Now proceed with copying the implementation files from the Claude artifacts and start developing!

```bash
cd ~/Projects/data-extraction-tool
code .
```
