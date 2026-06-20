#!/usr/bin/env bash
set -e

echo "========================================="
echo "Starting Mafia-AI Service"
echo "========================================="

# Get model name from environment variable (default: llama3.1:8b)
MODEL="${OLLAMA_MODEL:-llama3.1:8b}"

# Start Ollama server in background for model management
echo "Starting Ollama server..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

# Wait for Ollama server to be ready
echo "Waiting for Ollama server to start..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✓ Ollama server is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "✗ Ollama server failed to start"
        kill $OLLAMA_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

echo "Checking if Ollama model '$MODEL' is available..."

# Check if model is already downloaded
if ollama list | grep -q "^${MODEL}"; then
    echo "✓ Model '$MODEL' is already available"
else
    echo "Downloading model '$MODEL'..."
    ollama pull "$MODEL"

    if [ $? -eq 0 ]; then
        echo "✓ Model '$MODEL' downloaded successfully"
    else
        echo "✗ Failed to download model '$MODEL'"
        kill $OLLAMA_PID 2>/dev/null || true
        exit 1
    fi
fi

echo "========================================="
echo "Starting Mafia-AI application..."
echo "========================================="

# Run the Flet application
exec watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- python -m src.main
