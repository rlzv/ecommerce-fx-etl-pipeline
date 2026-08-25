# E-commerce FX ETL Pipeline

An end-to-end data engineering project that ingests e-commerce order lines, cleans and
validates inconsistent source data, loads daily foreign-exchange rates, and builds analytical
tables in EUR.

## Technology

- Python 3.12+
- PostgreSQL 17
- Docker Compose
- SQL transformations
- Pytest, Ruff, and mypy
- GitHub Actions

## Local bootstrap

Copy the environment template and start PostgreSQL:

```bash
cp .env.example .env
docker compose up -d postgres
docker compose ps
```

Create and activate a virtual environment on Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Apply migrations and verify the database connection:

```bash
ecommerce-etl db-check
ecommerce-etl migrate
```

## Branching

Feature branches are created from `develop` and merged through pull requests. The `main`
branch contains the release-ready version.
