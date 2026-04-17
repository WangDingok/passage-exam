#!/bin/bash

# Define ports
BACKEND_PORT=8001
FRONTEND_PORT=5174
NGROK_DOMAIN="gerardo-nonliquefying-celine.ngrok-free.app"

echo "=========================================="
echo "🧹 Clearing ports $BACKEND_PORT and $FRONTEND_PORT..."
echo "=========================================="
# Using npx to safely cross-platform kill ports
npx --yes kill-port $BACKEND_PORT $FRONTEND_PORT

echo ""
echo "=========================================="
echo "🚀 Starting Backend (Port $BACKEND_PORT)..."
echo "=========================================="
# Assuming virtual environment is already activated, or it will use the current python
python -m src.main serve --host 127.0.0.1 --port $BACKEND_PORT &
BACKEND_PID=$!

echo ""
echo "=========================================="
echo "⚛️ Starting Frontend (Port $FRONTEND_PORT)..."
echo "=========================================="
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both servers are starting up!"
echo "📡 Ngrok domain allowed: $NGROK_DOMAIN"
echo "🛑 Press Ctrl+C to stop both servers."

# Wait for background processes so Ctrl+C can kill them
wait $BACKEND_PID $FRONTEND_PID
