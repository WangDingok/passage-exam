#!/bin/bash

# Define ports
BACKEND_PORT=8001
FRONTEND_PORT=5174
NGROK_DOMAIN="gerardo-nonliquefying-celine.ngrok-free.app"

echo "=========================================="
echo "Clearing ports $BACKEND_PORT and $FRONTEND_PORT..."
echo "=========================================="
# Using npx to safely cross-platform kill ports
npx --yes kill-port $BACKEND_PORT $FRONTEND_PORT

echo ""
echo "=========================================="
echo "Installing Dependencies..."
echo "=========================================="
echo "Checking Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "Checking Frontend dependencies..."
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    npm install
    cd ..
fi

echo ""
echo "=========================================="
echo "Starting Backend (Port $BACKEND_PORT)..."
echo "=========================================="
# Assuming virtual environment is already activated, or it will use the current python
python -m src.main serve --host 127.0.0.1 --port $BACKEND_PORT &
BACKEND_PID=$!

echo ""
echo "=========================================="
echo "Starting Frontend (Port $FRONTEND_PORT)..."
echo "=========================================="
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================="
echo "Starting Ngrok (Domain: $NGROK_DOMAIN)..."
echo "=========================================="
ngrok http --domain=$NGROK_DOMAIN $FRONTEND_PORT &
NGROK_PID=$!

echo ""
echo "All services are starting up!"
echo "Ngrok URL: https://$NGROK_DOMAIN"
echo "Press Ctrl+C to stop everything."

# Wait for background processes so Ctrl+C can kill them
wait $BACKEND_PID $FRONTEND_PID $NGROK_PID
