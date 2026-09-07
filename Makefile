.PHONY: help demo demo-cli evaluate rebuild test all

PYTHON ?= python

help:
	@echo "GhostPen - BEC Detection via Writing-Style Analysis"
	@echo ""
	@echo "Available commands:"
	@echo "  make demo        Run Streamlit interactive inbox demo"
	@echo "  make demo-cli    Run terminal CLI demonstration on sample messages"
	@echo "  make evaluate    Run complete benchmark evaluation & generate artifacts"
	@echo "  make rebuild     Rebuild profiles and nulls from data/prepared/"
	@echo "  make test        Run unit and smoke test suite"
	@echo "  make all         Rebuild profiles, run evaluation, and execute tests"

demo:
	$(PYTHON) -m streamlit run app/app.py

demo-cli:
	$(PYTHON) -m src.cli --demo

evaluate:
	$(PYTHON) -m src.evaluate

rebuild:
	$(PYTHON) -m src.profile --rebuild

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

all: rebuild evaluate test
