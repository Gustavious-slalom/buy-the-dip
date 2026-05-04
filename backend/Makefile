dev:
	uvicorn app.main:app --reload --port 8000
test:
	pytest -v
smoke:
	FIXTURES_MODE=1 python -m app.cli "analyze AAPL"
