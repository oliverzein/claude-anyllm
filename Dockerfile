FROM python:3.13-slim

RUN addgroup --system --gid 1001 appuser \
    && adduser --system --uid 1001 --gid 1001 appuser

WORKDIR /app

COPY pyproject.toml ./
COPY atlas_proxy/ atlas_proxy/

RUN pip install --no-cache-dir -e . \
    && rm -rf /root/.cache/pip

ENV ATLAS_PROXY_PORT=8082

EXPOSE 8082

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/health')" || exit 1

CMD ["atlas-anthropic-proxy"]
