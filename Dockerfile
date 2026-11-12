
FROM astral/uv:alpine

ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

ENV UV_CACHE_DIR=/app/.cache/uv
ENV UV_PYTHON_INSTALL_DIR=/app/.uv/python
ENV UV_PYTHON=3.12

# Install system dependencies required to compile Python packages
RUN apk add --no-cache \
    build-base \
    python3-dev \
    linux-headers \
    zstd-dev

# Create non-root application user
RUN addgroup -g ${APP_GID} -S app \
    && adduser -S -D -H -u ${APP_UID} -G app app

# Copy dependency definitions
COPY pyproject.toml uv.lock ./

# Copy application files
COPY app/ ./app/
COPY knowledge/ ./knowledge/

# Install Python dependencies
RUN uv sync --no-dev

# Prepare directories and permissions
RUN mkdir -p ${UV_CACHE_DIR} /app/logs \
    && chown -R ${APP_UID}:${APP_GID} /app

# Run as non-root user
USER ${APP_UID}:${APP_GID}

EXPOSE 9000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
