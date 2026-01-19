# Development Setup

## Prerequisites
- Python 3.12+
- Git

## Setup

### Windows PowerShell
```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
pytest
ruff check .
```

### Cross-platform (Linux/macOS)
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
pytest
ruff check .
```

## Running the Server
```bash
cd backend
venv\Scripts\activate  # Windows
source venv/bin/activate  # Unix
uvicorn app.main:app --reload
```

## Running Tests
```bash
cd backend
pytest
```

## Linting and Formatting
```bash
cd backend
ruff check .
ruff format .