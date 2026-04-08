FROM ubuntu:24.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    gh \
    nodejs \
    npm \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user for agent
RUN useradd -m -s /bin/bash agent
USER agent
WORKDIR /home/agent

# Copy agent scripts
COPY --chown=agent:agent scripts/ /home/agent/scripts/
COPY --chown=agent:agent config/ /home/agent/config/

# Default: run the polling script
CMD ["bash", "/home/agent/scripts/poll_jira.sh"]
