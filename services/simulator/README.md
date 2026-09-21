# Simulator

Имитация датчиков завода строительных материалов. Не оборудование: процесс сам раз в несколько секунд
спрашивает catalog, кто `active`, и шлёт выдуманные числа в telemetry.

Порт: 8085. Резервные цеха не трогает — их catalog не отдаёт при `status=active`.

## Запуск (catalog на 8081 и telemetry на 8082 уже должны работать)

```bash
source ~/smart_factory/.venv/bin/activate
python -m pip install -r ~/smart_factory/services/simulator/requirements.txt
cd ~/smart_factory/services/simulator
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

Через 5–10 секунд:

```bash
curl http://127.0.0.1:8085/health
curl http://127.0.0.1:8085/status
curl http://127.0.0.1:8082/readings/latest
```

В `latest` должны появиться разные площадки, не только ручной POST.
