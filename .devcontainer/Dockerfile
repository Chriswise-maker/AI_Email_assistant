FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# Python 3.11 + pip
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Aliases damit "python" und "pip" ohne Versionsnummer funktionieren
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Sicherheit: non-root User (devcontainers base image hat "vscode" User schon)
USER vscode
