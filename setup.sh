#!/bin/bash
set -e

echo "=== Fabric Visualizer Setup ==="
echo ""

# Backend setup
echo "Installing Python dependencies..."
cd "$(dirname "$0")/backend"
pip install -r requirements.txt --quiet

# Frontend setup
echo "Installing frontend dependencies..."
cd "$(dirname "$0")/../frontend"
npm install --silent

echo ""
echo "Setup complete!"
echo ""
echo "To start the app, run: ./run.sh"
echo ""
echo "Optional: Set these environment variables for AI-powered visualization:"
echo "  export FV_REPLICATE_API_TOKEN=your_token_here"
echo ""
