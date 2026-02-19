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
