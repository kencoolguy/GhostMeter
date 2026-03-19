# Contributing to GhostMeter

Thank you for your interest in contributing to GhostMeter!

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16 (or use Docker)

### Getting Started

```bash
# Clone the repo
git clone https://github.com/kencoolguy/GhostMeter.git
cd GhostMeter

# Start PostgreSQL
docker compose up -d postgres

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## Branch Naming

- Features: `feature/<description>-YYYYMMDD`
- Bug fixes: `fix/<description>`
- Refactoring: `refactor/<description>`

**Never commit directly to `main` or `dev`.**

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — adding/updating tests
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `chore:` — maintenance tasks
- `ci:` — CI/CD changes

## Running Tests

```bash
# Backend
cd backend
pytest -v

# Frontend type check
cd frontend
npx tsc --noEmit

# Frontend E2E
cd frontend
npm run build
npx playwright test
```

## Code Style

### Python (Backend)

- PEP 8, max line length 100
- Type hints on all function signatures
- Google-style docstrings on public functions
- Lint with `ruff check .`

### TypeScript (Frontend)

- Strict mode enabled
- Functional components only
- Named exports (except pages)
- `const` by default

## Pull Requests

1. Create a feature branch from `dev`
2. Make your changes with tests
3. Ensure all tests pass and linting is clean
4. Submit a PR to `dev`
5. Wait for review before merging

## Project Structure

See the main [README.md](README.md) for project structure details.
