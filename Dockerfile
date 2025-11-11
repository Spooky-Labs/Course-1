FROM gcr.io/the-farm-neutrino-315cd/base-with-models:0.0.2

WORKDIR /workspace

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy runner script
COPY runner.py ./workspace
COPY symbols.txt ./workspace
COPY ./agent/agent.py /workspace/agent
COPY ./data /workspace/data

# Security: Run as non-root user
# REQUIRED: Copy cache to non-root user
RUN useradd -m appuser && \
    mkdir -p /home/appuser/.cache && \
    cp -r /root/.cache/huggingface /home/appuser/.cache/ && \
    chown -R appuser:appuser /home/appuser/.cache/huggingface
    
USER appuser

# Default command (will be overridden at runtime)
CMD ["python", "runner.py"]
