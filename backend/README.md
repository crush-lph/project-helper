# project-helper backend

FastAPI + LangChain + SQLite backend for project-helper.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set `DEEPSEEK_API_KEY` to enable DeepSeek-powered report generation and code Q&A. Without it, the app still runs with deterministic local analysis for testing.
