# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed
FROM ${PYTHON_IMAGE} AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY services/telemetry/requirements.lock ./requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 factory \
    && useradd --uid 10001 --gid factory --no-create-home factory \
    && mkdir -p /opt/factory/data \
    && chown 10001:10001 /opt/factory/data
WORKDIR /opt/factory/services/telemetry
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=10001:10001 services/telemetry/app ./app
COPY --chown=10001:10001 data/equipment-documents/*.pdf /opt/factory/data/equipment-documents/
USER 10001:10001
EXPOSE 8082
HEALTHCHECK --interval=10s --timeout=4s --start-period=15s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=3).read()"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--no-access-log"]
