# Catalog

Источник правды о заводе: площадки, КТП, кого какая подстанция питает, маршруты выпуска.

Почему отдельный сервис: список цехов меняется редко. Telemetry, ktp и production
не должны каждый хранить свою копию — иначе через месяц «резервный цех» будет
только в одном месте.

## API

| Метод | Путь | Что отдаёт |
|---|---|---|
| GET | `/health` | жив ли процесс |
| GET | `/sites` | все площадки |
| GET | `/sites/{id}` | одна площадка |
| GET | `/ktp` | только КТП |
| GET | `/topology` | КТП → список питаемых площадок |
| GET | `/routes` | маршруты сухой смеси и эмульсии |

## Запуск на lab VM

Из корня репозитория:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/catalog/requirements.txt
cd services/catalog
uvicorn app.main:app --host 0.0.0.0 --port 8081
```
