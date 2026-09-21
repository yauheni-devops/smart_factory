# Production

Заявки на выпуск и контроль план/факт.

Маршруты читает из catalog (сухая смесь / эмульсия), сам каталог не дублирует.
Порт: 8083.
Контракт: `packages/contracts/schemas/order.schema.json`.

## MVP API

Сервис использует маршруты из `catalog` и пока хранит заявки в памяти процесса.

```bash
cd services/production
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8083
```

Примеры:

```bash
curl http://127.0.0.1:8083/routes
curl -X POST http://127.0.0.1:8083/orders -H "Content-Type: application/json" -d '{"product_id":"dry_mix","qty_planned":100}'
curl http://127.0.0.1:8083/orders
```
