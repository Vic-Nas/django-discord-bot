#!/usr/bin/env python3
"""
Ultra-simple standalone health check server
This helps debug if the container itself is responsive
"""
import socket
import threading
import sys

def simple_http_server():
    """Minimal HTTP server that responds immediately"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 9999))
    server.listen(1)
    
    print("[HEALTH_SERVER] Listening on 0.0.0.0:9999", flush=True)
    sys.stdout.flush()
    
    while True:
        try:
            client, addr = server.accept()
            print(f"[HEALTH_SERVER] Connection from {addr}", flush=True)
            sys.stdout.flush()
            
            request = client.recv(1024).decode('utf-8', errors='ignore')
            print(f"[HEALTH_SERVER] Request: {request.split(chr(13))[0]}", flush=True)
            sys.stdout.flush()
            
            response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
            client.sendall(response)
            client.close()
            
            print("[HEALTH_SERVER] Response sent", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[HEALTH_SERVER] Error: {e}", flush=True)
            sys.stdout.flush()

if __name__ == '__main__':
    # Run in background thread
    thread = threading.Thread(target=simple_http_server, daemon=True)
    thread.start()
    
    # Keep main thread alive
    import time
    while True:
        time.sleep(1)
