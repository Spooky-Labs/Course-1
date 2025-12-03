# Use the GPU-enabled base image with pre-cached models
# This image contains PyTorch with CUDA 11.8 + HuggingFace models
# Version 0.2.0: GPU support via pytorch/pytorch:2.4.0-cuda11.8-cudnn9-runtime
FROM gcr.io/the-farm-neutrino-315cd/base-with-models:0.2.0

# Accept models directory from build (populated by detect_models + GCS copy)
# If provided, these models supplement/override base image models
# NOTE: Must be a RELATIVE path (relative to build context) for Docker COPY
ARG MODELS_DIR=hf_cache/hub

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

# Copy detected models from build context (if any)
# This directory is populated by the Cloud Build detect-models + copy-models-from-gcs steps
COPY ${MODELS_DIR}* /tmp/detected_models/

# Create non-root user and copy models to read-only location
# Models will be copied to tmpfs-mounted /home/appuser/.cache at runtime
# This allows --read-only filesystem while HuggingFace can write lock files
# Priority: detected models (from GCS cache) > base image models
RUN useradd -m appuser && \
      mkdir -p /opt/models/.cache/huggingface/hub && \
      mkdir -p /home/appuser/.cache && \
      # First copy base image models (fallback)
      cp -r /root/.cache/huggingface/* /opt/models/.cache/huggingface/ 2>/dev/null || true && \
      # Then overlay detected models (if any) - these take priority
      if [ -d /tmp/detected_models ] && [ "$(ls -A /tmp/detected_models 2>/dev/null)" ]; then \
          echo "Copying detected models from build..."; \
          cp -r /tmp/detected_models/* /opt/models/.cache/huggingface/hub/ 2>/dev/null || true; \
      fi && \
      rm -rf /tmp/detected_models && \
      chown -R appuser:appuser /opt/models/.cache/huggingface /home/appuser/.cache

# Create entrypoint script to copy models from read-only location to writable tmpfs
# This runs at container startup BEFORE the main application
# Required because: --read-only makes filesystem immutable, but HuggingFace needs
# to write .lock files when loading models. tmpfs mount provides writable RAM-backed storage.
RUN echo '#!/bin/sh' > /entrypoint.sh && \
      echo 'set -e' >> /entrypoint.sh && \
      echo '# Copy models from /opt (baked into image, read-only) to /home/appuser/.cache (tmpfs, writable)' >> /entrypoint.sh && \
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
