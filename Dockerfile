FROM python:3.9-slim

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
RUN useradd -m appuser
USER appuser

# Default command (will be overridden at runtime)
CMD ["python", "runner.py"]