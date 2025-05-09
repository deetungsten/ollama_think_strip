# Llama.cpp to Ollama API Proxy

This setup allows you to run a Llama.cpp server while maintaining compatibility with the Home Assistant Ollama integration. The proxy translates API requests from the Ollama format to the Llama.cpp format and back.

## Overview

Home Assistant has an official Ollama integration but not one for Llama.cpp. This solution lets you:

1. Run Llama.cpp server (better performance than Ollama)
2. Use Home Assistant's Ollama integration
3. Translate API requests/responses between the two formats seamlessly

## Setup Instructions

### 1. Prerequisites

- Docker and Docker Compose installed
- A compatible GGUF model for Llama.cpp

### 2. Configuration

1. Create a `models` directory and place your GGUF model file(s) there
2. Create a `logs` directory for Nginx logs
3. Place the `llama_cpp_proxy.conf` and `docker-compose.yml` files in your project directory
4. Update the `docker-compose.yml` file with the path to your model and any specific Llama.cpp parameters needed

### 3. Starting the Service

```bash
# Create necessary directories
mkdir -p models logs

# Start the services
docker-compose up -d
```

### 4. Configure Home Assistant

Configure the Ollama integration in Home Assistant to point to your server's IP address:

- Host: YOUR_SERVER_IP
- Port: 11434 (default)

## API Translation Details

The proxy handles the following mappings:

| Ollama API | Llama.cpp API |
|------------|--------------|
| `/api/generate` | `/completion` |
| `/api/tags` | `/models` |

Parameters are translated between formats as needed.

## Troubleshooting

Check the logs for detailed information about requests and responses:

```bash
# View Nginx logs
docker-compose logs nginx

# View Llama.cpp server logs
docker-compose logs llamacpp
```

## Customization

You can modify the `llama_cpp_proxy.conf` file to:

- Add support for more API endpoints
- Adjust parameter mappings between Ollama and Llama.cpp
- Configure additional filters like the think tag removal
- Change CPU/GPU utilization or other performance settings

## Performance Notes

Llama.cpp typically offers better performance than Ollama for the same models, particularly with optimizations like quantization and GPU offloading. Use the `command` section in the docker-compose.yml file to adjust Llama.cpp parameters for your hardware.