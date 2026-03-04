# Unified AI

An open-source, production-ready backend for a unified AI API server. It includes a secure API key management system and proxies requests to a local Ollama instance.

## Features

- **Secure API Key System**: Generate, revoke, and manage API keys with names.
- **Usage Tracking**: Monitor API key usage, including request frequency, models used, and processing times.
- **Ollama Integration**: Forwards requests to a local Ollama LLM instance, with the model defined via environment variables.
- **Internal & Public Routes**: Internal endpoints for key management are strictly firewalled to `localhost`.
- **Production Ready**: Includes rate limiting, structured logging, and async architecture.

---

## Deployment to Ubuntu VM from GitHub

This guide provides end-to-end instructions for deploying the Unified AI server on a fresh Ubuntu VM.

### 1. System Prerequisites

First, update your package list and install Python, `pip`, `venv`, and `git`.

```bash
sudo apt update
sudo apt install -y python3-pip python3.11-venv git curl
```

### 2. Clone and Set Up the Project

1.  **Clone the Repository**
    ```bash
    git clone <YOUR_GITHUB_REPOSITORY_URL> unified-ai
    cd unified-ai
    ```

2.  **Create and Activate Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Install and Configure Ollama

1.  **Install Ollama**
    ```bash
    curl -fsSL https://ollama.com/install.sh | sh
    ```

2.  **Configure Environment**
    Copy the example environment file and set the `OLLAMA_MODEL` you intend to use.
    ```bash
    cp .env.example .env
    ```
    Open `.env` with a text editor (like `nano` or `vim`) and ensure `OLLAMA_MODEL` is set to your desired model (e.g., `llama3.2:latest`).

3.  **Pull the LLM Model**
    Pull the model specified in your `.env` file.
    ```bash
    ollama run $(grep OLLAMA_MODEL .env | cut -d '=' -f2)
    ```
    *This command reads the model name directly from your `.env` file. Type `/bye` to exit the chat; the Ollama server will keep running.* 

### 4. Run the Application

Start the Unified AI server using `uvicorn`.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Your API is now running. You can access it from within the VM at `http://localhost:8000`.

---

## API Usage

### Generate API Key (Internal Only)

**Note:** This must be run from the VM itself.

```bash
curl -X POST http://localhost:8000/internal/generate-key \
  -H "Content-Type: application/json" \
  -d '{"name": "My First App"}'
```

### Chat with LLM

```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: YOUR_FULL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      { "role": "user", "content": "Explain quantum computing in one sentence." }
    ],
    "stream": false
  }'
```

### View Usage Stats (Internal Only)

```bash
curl http://localhost:8000/internal/usage-stats/{key_id}
```
