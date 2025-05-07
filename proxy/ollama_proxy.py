#!/usr/bin/env python3
"""
Flask proxy that
• forwards any HTTP verb/path to the local Ollama service
• streams responses token-by-token
• removes every <think> … </think> block, no matter what's inside
• handles Unicode escape sequences for think tags
"""
import os, json, re, requests, logging
from flask import Flask, Response, request, stream_with_context, g
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

logger.info(f"Starting Ollama proxy with target URL: {OLLAMA_HOST}")
logger.info(f"Debug mode: {DEBUG_MODE}")

# Clean up resources on request completion
@app.teardown_request
def cleanup_request(exception=None):
    """Ensure proper cleanup of resources when request ends."""
    if hasattr(g, 'upstream_response'):
        logger.debug("Cleaning up upstream response in teardown")
        g.upstream_response.close()

# Buffer class for handling think tags across chunks
class ThinkTagBuffer:
    def __init__(self):
        self.buffer = ""
        
    def process_chunk(self, chunk):
        """Process a chunk of data, filtering out think tags."""
        # Add chunk to buffer
        self.buffer += chunk
        
        output = ""
        
        while True:
            # Find the next potential tag start (both literal and escaped forms)
            literal_start = self.buffer.find("<think")
            escaped_start = self.buffer.find("\\u003cthink")
            
            # Determine which tag starts first, if any
            if literal_start == -1 and escaped_start == -1:
                # No more think tags, output all except last few chars
                # (keeping a safety buffer for potential partial tags)
                if len(self.buffer) > 1024:
                    output += self.buffer[:-1024]
                    self.buffer = self.buffer[-1024:]
                break
                
            start = literal_start if literal_start != -1 and (escaped_start == -1 or literal_start < escaped_start) else escaped_start
            is_literal = (start == literal_start)
            
            # Output content before the tag
            if start > 0:
                output += self.buffer[:start]
                self.buffer = self.buffer[start:]
                # Reset indices since we modified the buffer
                start = 0
            
            # Determine appropriate end tag based on type
            end_tag = "</think>" if is_literal else "\\u003c/think\\u003e"
            end = self.buffer.find(end_tag, start)
            
            if end == -1:
                # No end tag yet, keep in buffer
                break
                
            # Remove the complete think tag and its content
            end += len(end_tag)
            if DEBUG_MODE:
                removed = self.buffer[:end]
                logger.debug(f"Filtered out think tag: {removed}")
            
            self.buffer = self.buffer[end:]
            
        return output
        
    def flush(self):
        """Output any remaining content in the buffer."""
        # Final pass to clean up any remaining think tags
        content = self.buffer
        # Apply regex substitutions for any remaining think tags
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL|re.I)
        content = re.sub(r'\\u003cthink.*?\\u003c/think\\u003e', '', content, flags=re.DOTALL|re.I)
        
        self.buffer = ""
        return content

@app.route("/health")
def health_check():
    """Health check endpoint."""
    try:
        response = requests.get(
            f"{OLLAMA_HOST}/api/version",
            timeout=5
        )
        return Response(
            response='{"status": "healthy", "target": "' + OLLAMA_HOST + '"}',
            status=200,
            content_type="application/json"
        )
    except Exception as e:
        error_msg = f"Health check failed: {str(e)}"
        logger.error(error_msg)
        return Response(
            response='{"status": "unhealthy", "error": "' + error_msg + '"}',
            status=503,
            content_type="application/json"
        )

@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def proxy(path):
    """Main proxy route that handles all requests."""
    # Construct the target URL
    target_url = urljoin(OLLAMA_HOST, path)
    
    # Forward headers (except Host)
    headers = {
        key: value 
        for key, value in request.headers 
        if key.lower() != "host"
    }
    
    # Include query parameters
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
        
    logger.info(f"Proxying {request.method} request to: {target_url}")
    if DEBUG_MODE:
        logger.debug(f"Headers: {headers}")
    
    try:
        # Get JSON body if present
        json_data = request.get_json(silent=True) if request.is_json else None
        if DEBUG_MODE and json_data:
            logger.debug(f"Request JSON: {json_data}")
        
        # Forward the request to Ollama
        g.upstream_response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            json=json_data if json_data is not None else None,
            data=request.get_data() if request.method in ("POST", "PUT") and json_data is None else None,
            stream=True,
            timeout=120  # 2 minute timeout
        )
        
        logger.info(f"Upstream status: {g.upstream_response.status_code}")
        
        # For error responses, return them directly
        if g.upstream_response.status_code >= 400:
            error_content = g.upstream_response.content.decode('utf-8')
            logger.error(f"Upstream error: {g.upstream_response.status_code}")
            logger.error(f"Error response: {error_content}")
            return Response(
                error_content,
                status=g.upstream_response.status_code,
                content_type=g.upstream_response.headers.get("Content-Type", "application/json")
            )
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to forward request: {str(e)}"
        logger.error(error_msg)
        return Response(
            response='{"error": "' + error_msg + '"}',
            status=502,
            content_type="application/json"
        )
    
    # Determine if this is a streaming response
    is_stream = True
    if json_data and 'stream' in json_data:
        is_stream = json_data.get('stream', True)  # Default to True
    
    if not is_stream:
        # Handle non-streaming responses
        content = g.upstream_response.content.decode("utf-8", errors="replace")
        # Filter out think tags
        filtered_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL|re.I)
        filtered_content = re.sub(r'\\u003cthink.*?\\u003c/think\\u003e', '', filtered_content, flags=re.DOTALL|re.I)
        
        if DEBUG_MODE and filtered_content != content:
            logger.debug(f"Filtered non-streaming content")
            
        return Response(
            filtered_content,
            status=g.upstream_response.status_code,
            headers=[(name, value) for name, value in g.upstream_response.headers.items() if name.lower() != "content-length"],
            content_type=g.upstream_response.headers.get("Content-Type", "application/json")
        )
    else:
        # Handle streaming responses
        def generate_filtered_response():
            buffer = ThinkTagBuffer()
            
            try:
                # Set initial connection state
                request.is_closed = False
                
                for chunk in g.upstream_response.iter_content(chunk_size=8192):
                    if getattr(request, 'is_closed', False):
                        logger.info("Request closed, stopping chunk generation")
                        return
                        
                    if chunk:
                        # Process chunk through the buffer
                        decoded_chunk = chunk.decode("utf-8", errors="replace")
                        if DEBUG_MODE:
                            logger.debug(f"Received chunk: {decoded_chunk}")
                        
                        filtered_output = buffer.process_chunk(decoded_chunk)
                        if filtered_output:
                            yield filtered_output.encode("utf-8")
                        
            except (GeneratorExit, ConnectionError):
                logger.info("Client disconnected")
                request.is_closed = True
                return
            except Exception as e:
                logger.error(f"Error in streaming response: {str(e)}")
                if not getattr(request, 'is_closed', False):
                    yield f"Error in streaming response: {str(e)}".encode()
            finally:
                # Flush any remaining content
                if not getattr(request, 'is_closed', False):
                    final_output = buffer.flush()
                    if final_output:
                        if DEBUG_MODE:
                            logger.debug(f"Final output: {final_output}")
                        yield final_output.encode("utf-8")
        
        return Response(
            stream_with_context(generate_filtered_response()),
            status=g.upstream_response.status_code,
            headers=[(name, value) for name, value in g.upstream_response.headers.items() if name.lower() != "content-length"],
            content_type=g.upstream_response.headers.get("Content-Type", "application/json")
        )

if __name__ == "__main__":
    port = int(os.getenv("PORT", "11434"))
    logger.info(f"Starting Ollama proxy server on http://0.0.0.0:{port}")
    logger.info(f"Forwarding requests to {OLLAMA_HOST}")
    app.run(host="0.0.0.0", port=port, debug=DEBUG_MODE)