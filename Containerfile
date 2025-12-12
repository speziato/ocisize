FROM python:3.14-alpine as base
WORKDIR /app

# Copy shared core
COPY src/core.py .

# Add non-root user
RUN adduser -D appuser && chown -R appuser:appuser /app

# Web UI variant
FROM base AS web
COPY --chown=appuser:appuser src/web.py .
COPY --chown=appuser:appuser src/index.html .
ENV HTTP_PORT=8080
EXPOSE ${HTTP_PORT}
CMD ["python", "web.py"]

# CLI variant
FROM base AS cli
COPY --chown=appuser:appuser src/cli.py .
ENTRYPOINT ["python", "cli.py"]