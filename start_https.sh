#!/usr/bin/env bash

# Check if certificate files exist
if [ ! -f "cert.pem" ] || [ ! -f "key.pem" ]; then
  echo "Certificate files not found. Generating new ones..."
  
  # Check if mkcert is installed
  if command -v mkcert &> /dev/null; then
    echo "Using mkcert to generate certificates..."
    mkcert -key-file key.pem -cert-file cert.pem localhost 127.0.0.1 ::1
  else
    echo "mkcert not found. Using OpenSSL instead..."
    # Use proper subject format for Windows
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout key.pem -out cert.pem \
      -subj "//C=US\ST=CA\L=Local\O=Development\OU=Dev\CN=localhost"
  fi
fi

# Launch Uvicorn with SSL
echo "Starting Uvicorn server with HTTPS..."
uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem 