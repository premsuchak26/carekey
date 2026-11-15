.PHONY: help install run test lint format typecheck docker-build docker-run clean

# Variables
PYTHON ?= python
UVICORN ?= uvicorn
RUFF ?= ruff
MYPY ?= mypy
PYTEST ?= pytest

help:
	@echo "CareKey Development Tasks:"
	@echo "  make install      Install production and development dependencies"
	@echo "  make run          Run the development server with hot reload"
	@echo "  make test         Execute pytest test suite"
	@echo "  make lint         Check code formatting and lint rules with ruff"
	@echo "  make format       Auto-format code and sort imports with ruff"
	@echo "  make typecheck    Run static type analysis with mypy"
	@echo "  make docker-build Build the non-root slim Docker image"
	@echo "  make docker-run   Run the Docker container locally on port 8000"
	@echo "  make clean        Remove temporary bytecode and cache directories"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements-dev.txt

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	$(PYTEST) -v

lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) check --fix .
	$(RUFF) format .

typecheck:
	$(MYPY) app tests

check: lint typecheck test

docker-build:
	docker build -t carekey:latest .

docker-run:
	docker run -p 8000:8000 --rm --name carekey-app carekey:latest

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
