.PHONY: catalog telemetry simulator production maintenance

catalog:
	cd services/catalog && uvicorn app.main:app --host 0.0.0.0 --port 8081

telemetry:
	cd services/telemetry && uvicorn app.main:app --host 0.0.0.0 --port 8082

simulator:
	cd services/simulator && uvicorn app.main:app --host 0.0.0.0 --port 8085

production:
	cd services/production && uvicorn app.main:app --host 0.0.0.0 --port 8083

maintenance:
	cd services/maintenance && uvicorn app.main:app --host 0.0.0.0 --port 8086


