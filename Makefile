.DEFAULT_GOAL := help
.PHONY: help install all ingest contracts silver split features gates train evaluate serve \
        readme test lint format typecheck check clean mssql-up mssql-down

PY := uv run
SRC := src/hcr

help:
	@echo "install    install the package and dev dependencies"
	@echo "all        run the full pipeline end to end (steps 1-8)"
	@echo "ingest     step 1  raw CSV to bronze Parquet"
	@echo "contracts  step 2  validate row counts, columns, dtypes, primary keys"
	@echo "silver     step 3  normalize sentinels, flip DAYS_*, emit missingness flags"
	@echo "split      step 4  stratified holdout split, writes holdout_ids.parquet"
	@echo "features   step 5  DuckDB two-stage aggregation to customer grain"
	@echo "gates      step 6  feature quality and leakage gates"
	@echo "train      step 7  baselines, LightGBM CV, calibration, threshold"
	@echo "evaluate   open the holdout exactly once and write the final report"
	@echo "serve      step 8  build star schema and load SQL Server"
	@echo "readme     fill README metrics from MLflow"
	@echo "test       run the test suite"
	@echo "check      lint, typecheck and test"
	@echo "mssql-up   start SQL Server on the port from .env"

install:
	uv sync --extra dev

all:
	$(PY) -m hcr.pipeline.run_all

ingest:
	$(PY) -m hcr.ingest.to_parquet

contracts:
	$(PY) -m hcr.contracts.validate_raw

silver:
	$(PY) -m hcr.silver.clean_application
	$(PY) -m hcr.silver.clean_history

split:
	$(PY) -m hcr.split.make_holdout

features:
	$(PY) -m hcr.features.build
	$(PY) -m hcr.features.select

gates:
	$(PY) -m hcr.quality.feature_gates
	$(PY) -m hcr.quality.leakage_checks

train:
	$(PY) -m hcr.modeling.baselines
	$(PY) -m hcr.modeling.train
	$(PY) -m hcr.modeling.calibrate
	$(PY) -m hcr.modeling.threshold
	$(PY) -m hcr.modeling.scorecard

evaluate:
	$(PY) -m hcr.evaluation.holdout_report
	$(PY) -m hcr.evaluation.fairness
	$(PY) -m hcr.evaluation.explain

serve:
	$(PY) -m hcr.serving.build_star
	$(PY) -m hcr.serving.load_sqlserver

readme:
	$(PY) -m reports.readme_fill

test:
	$(PY) -m pytest

lint:
	$(PY) ruff check .

format:
	$(PY) ruff format .
	$(PY) ruff check --fix .

typecheck:
	$(PY) mypy $(SRC)

check: lint typecheck test

clean:
	rm -rf data/bronze/* data/silver/* data/features/* data/splits/*

mssql-up:
	docker compose up -d

mssql-down:
	docker compose down
