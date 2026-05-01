# project-helper 测试与发布 Checklist

每次修改完成后，至少执行本 checklist 中和改动范围相关的检查。改到核心链路、关键函数或依赖时，执行完整检查。

## 核心链路

- [ ] 仓库地址输入后可以规范化为 `https://host/owner/repo`，非法地址返回 400。
- [ ] 创建项目后写入 SQLite，重复创建同一仓库命中已有项目。
- [ ] 分析流按 `clone -> scan -> summarize -> done` 推进，失败时项目状态变为 `failed`。
- [ ] 未配置 `DEEPSEEK_API_KEY` 时可以生成本地静态分析报告。
- [ ] 已完成分析的项目再次分析时走缓存，不重复克隆和扫描。
- [ ] 问答接口拒绝空问题；无 LLM key 时使用本地搜索 fallback。
- [ ] 前端可以创建任务、展示 SSE 进度、渲染报告，并在 ready 后启用问答。

## 必跑命令

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

```bash
cd frontend
npm install
npm run build
```

## 改动后自检

- [ ] 新增或修改关键函数时，同步补充 unit test。
- [ ] 修改 API 行为、状态流转、缓存逻辑或 fallback 行为时，同步补充 E2E test。
- [ ] 测试不依赖真实 GitHub 克隆、真实 LLM 调用或本机已有缓存。
- [ ] 错误信息仍然对中文用户可读。
- [ ] 不提交 `.env`、`.project-helper-data/`、`node_modules/`、`dist/` 或测试缓存。
