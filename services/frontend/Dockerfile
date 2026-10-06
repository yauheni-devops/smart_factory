# syntax=docker/dockerfile:1
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:stable-alpine@sha256:ed04ec1ff34502c339ee5c3ae3f855442398edc1d05591e2b98981dcbbd20b1e
FROM ${NGINX_IMAGE}
COPY services/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY services/frontend/static /usr/share/nginx/html
COPY data/equipment-documents/*.pdf /usr/share/nginx/html/equipment-documents/
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=4s --start-period=10s --retries=6 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/health"]
