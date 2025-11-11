# Use the base image with pre-cached models
# This image contains all HuggingFace models downloaded during build
FROM gcr.io/the-farm-neutrino-315cd/base-with-models:0.0.2

# Set working directory
WORKDIR /workspace

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy runner script
COPY runner.py ./workspace
COPY symbols.txt ./workspace

# Copy agent code (mounted from Cloud Storage during build)
COPY ./agent /workspace/agent

# Copy data files (mounted during build)
COPY ./data /workspace/data

# Create non-root user and copy models to read-only location
# Models will be copied to tmpfs-mounted /home/appuser/.cache at runtime
# This allows --read-only filesystem while HuggingFace can write lock files
RUN useradd -m appuser && \
      mkdir -p /opt/models/.cache && \
      cp -r /root/.cache/huggingface /opt/models/.cache/ && \
      chown -R appuser:appuser /opt/models/.cache/huggingface

RUN echo '#!/bin/sh' > /entrypoint.sh && \
      echo 'set -e' >> /entrypoint.sh && \
      echo '# Copy models from /opt (baked into image, read-only) to /home/appuser/.cache (tmpfs, writable)' >> /entrypoint.sh && \
      echo 'mkdir -p /home/appuser/.cache' >> /entrypoint.sh && \
      echo 'cp -r /opt/models/.cache/huggingface /home/appuser/.cache/' >> /entrypoint.sh && \
      echo '# Execute the CMD (runner.py)' >> /entrypoint.sh && \
      echo 'exec "$@"' >> /entrypoint.sh && \
      chmod +x /entrypoint.sh

# Make entrypoint executable
RUN chmod +x /entrypoint.sh
    
# Set HF_HOME to point to writable tmpfs location
# Base image sets HF_HOME=/root/.cache/huggingface
# Must override because: 1) Running as appuser, not root 2) Offline mode requires explicit path
ENV HF_HOME=/home/appuser/.cache/huggingface

# Switch to non-root user for security
USER appuser

# Set entrypoint to copy models before running app
ENTRYPOINT ["/entrypoint.sh"]
  
# Default command (will be overridden at runtime)
CMD ["python", "-u", "runner.py"]
