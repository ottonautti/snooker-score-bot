# 1. Base Stage
FROM python:3.12-slim

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED=True

# Copy only dependency-related files first to leverage Docker layer caching
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

# Copy the rest of the application source code (only whats isnide src/)
COPY src/ ./

# Run the application
CMD ["/bin/sh", "-c", "exec uvicorn --port $PORT --host 0.0.0.0 snooker_score_bot.main:app --workers 1"]