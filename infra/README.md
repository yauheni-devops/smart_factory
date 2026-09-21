# Infra

Здесь находятся локальная инфраструктура данных и мониторинга; Kubernetes и Argo CD добавим следующим этапом.

Сейчас сервисы запускаются процессами Python на lab VM.
Имена и порты уже зафиксированы — Compose просто повторит их:

| Сервис | Порт |
|---|---|
| frontend (NGINX, статические страницы и API proxy) | 8080 |
| catalog | 8081 |
| telemetry | 8082 |
| production | 8083 |
| ktp | 8084 |
| simulator | 8085 |
| maintenance | 8086 |

`docker-compose.yml` поднимает PostgreSQL, Prometheus и Grafana. API-сервисы пока запускаются отдельными процессами на хосте. Конфигурации scrape и автоматически загружаемые Grafana dashboards находятся в `infra/observability/`.

Frontend можно собрать и запустить контейнером из корня проекта:

```powershell
docker compose -f infra/docker-compose.yml up -d --build frontend
```

Откройте `http://127.0.0.1:8080/ui`. Контейнер NGINX отдаёт страницы и схему,
а `/ui/data`, `/ui/production`, `/readings` и `/metrics` проксирует в telemetry
на хосте (`8082`). Поэтому API-сервисы нужно запустить отдельно и привязать к
`0.0.0.0`; для связи frontend-контейнера с хостом используется `host-gateway`.
