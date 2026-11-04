.PHONY: test test-detector test-ingestor eval up down demo logs

test: test-detector test-ingestor

test-detector:
	cd detector && python -m unittest discover -s tests -t . -v

test-ingestor:
	cd ingestor && node --test

eval:
	cd detector && python evaluate.py --seeds 5

up:
	docker compose up -d --build

down:
	docker compose down -v

demo:
	python scripts/send_test_transactions.py

logs:
	docker compose logs -f detector
