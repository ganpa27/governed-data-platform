# ─────────────────────────────────────────────────────────────────────────────
#  Makefile — Governed Data Platform
#  Run from the governed-data-platform/ directory.
#
#  Commands:
#    make run          →  Start FastAPI backend only (port 8000)
#    make run-all      →  Start BOTH Flask (5001) + FastAPI (8000)
#    make install      →  Install FastAPI dependencies
#    make install-all  →  Install dependencies for BOTH projects
# ─────────────────────────────────────────────────────────────────────────────

FASTAPI_DIR := $(shell pwd)
FLASK_DIR   := $(FASTAPI_DIR)/../flask-governed-api

VENV        := $(FASTAPI_DIR)/venv
FLASK_VENV  := $(FLASK_DIR)/venv

PYTHON      := $(VENV)/bin/python
UVICORN     := $(VENV)/bin/uvicorn
FLASK_PY    := $(FLASK_VENV)/bin/python

.PHONY: run run-all install install-all help

## Start FastAPI backend only (port 8000)
run:
	@echo "▶  Starting FastAPI Backend → http://localhost:8000/docs"
	cd $(FASTAPI_DIR) && $(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

## Start BOTH Flask (port 5001) AND FastAPI (port 8000)
run-all:
	@echo "▶  Starting ALL services (Flask + FastAPI)..."
	@bash "$(FASTAPI_DIR)/start.sh"

## Install FastAPI dependencies
install:
	pip install -r $(FASTAPI_DIR)/requirements.txt

## Install dependencies for BOTH projects
install-all:
	pip install -r $(FASTAPI_DIR)/requirements.txt
	pip install -r $(FLASK_DIR)/requirements.txt

## Show available commands
help:
	@echo ""
	@echo "  make run          →  FastAPI backend only   (http://localhost:8000)"
	@echo "  make run-all      →  Flask + FastAPI both   (5001 + 8000)"
	@echo "  make install      →  Install FastAPI deps"
	@echo "  make install-all  →  Install all deps"
	@echo ""
