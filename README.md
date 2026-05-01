# project-helper

项目学习助手：输入 GitHub 仓库地址，自动克隆并分析源码，生成通俗易懂的项目报告，并支持基于源码工具的交互式问答。

## Tech Stack

- Backend: Python, FastAPI, LangChain, SQLite, DeepSeek-compatible OpenAI API
- Frontend: Vue 3, Vite, marked, highlight.js, lucide icons

## Run Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set `DEEPSEEK_API_KEY` in `backend/.env` to enable DeepSeek-powered analysis and agent answers. Without it, the app still runs with local static analysis.

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Features

- GitHub repo cloning with normalized URL validation
- SQLite project cache to avoid repeated analysis
- Server-Sent Events for realtime analysis progress
- Markdown report rendering with syntax-highlighted code blocks
- LangChain agent tools: list tree, read file, search code
- Streaming Q&A endpoint with a no-key local fallback
