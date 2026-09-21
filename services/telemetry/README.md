# Telemetry

Приём показаний датчиков. Список площадок **не хранит** — спрашивает catalog (порт 8081).
История пока в памяти процесса: перезапуск uvicorn обнуляет данные. PostgreSQL — следующий этап.

Порт: 8082.

## API

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/health` | жив ли процесс |
| POST | `/readings` | записать одно показание |
| GET | `/readings` | последние показания |
| GET | `/ui` | Стартовая страница с переходами в мониторинг и ПТО |
| GET | `/monitoring` | HTML-схема с датчиками |
| GET | `/production` | Отдельная страница выпуска план/факт |
| GET | `/alerts` | Отдельная страница аварий и предупреждений по телеметрии |
| GET | `/ui/data` | JSON для этого экрана |
| GET | `/ui/production` | Сводка план/факт активных заявок сервиса выпуска |

Стартовая страница показывает выпуск по активным заявкам `services/production` (порт 8083), а в блоке предупреждений проверяет полноту и свежесть данных датчиков. Предупреждения по технологическим пределам появятся после настройки утверждённых уставок; сейчас они не вычисляются.

Резервные цеха (`status: reserved`) показания не принимают.

## Запуск на lab (второе окно, catalog уже на 8081)

Из корня, тот же `.venv`:

```bash
source ~/smart_factory/.venv/bin/activate
python -m pip install -r ~/smart_factory/services/telemetry/requirements.txt
cd ~/smart_factory/services/telemetry
uvicorn app.main:app --host 0.0.0.0 --port 8082
```

Проверка:

```bash
curl http://127.0.0.1:8082/health

curl -X POST http://127.0.0.1:8082/readings \
  -H "Content-Type: application/json" \
  -d '{"site_id":"workshop-dry-mix-1","metric":"power_kw","value":120.5,"unit":"kW"}'

curl http://127.0.0.1:8082/readings/latest
```
