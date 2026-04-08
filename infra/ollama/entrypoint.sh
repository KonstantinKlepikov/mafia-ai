#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!

# Wait for the server to be ready
echo "Waiting for Ollama to start..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama is ready."

# Pull model only if not already present
MODEL="${OLLAMA_MODEL:-mistral}"
if ! ollama list | grep -q "^${MODEL}"; then
    echo "Pulling model: ${MODEL}"
    ollama pull "${MODEL}"
    echo "Model ${MODEL} pulled successfully."
else
    echo "Model ${MODEL} already present, skipping pull."
fi

# Wait for the background server process to exit
wait "$OLLAMA_PID"
