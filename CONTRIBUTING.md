# Contributing to NewsBlog AI

Thank you for taking the time to contribute. All types of contributions are welcome — bug reports, feature requests, documentation improvements, and code.

---

## Getting started

### 1. Fork and clone

```bash
git clone https://github.com/your-username/newsblog-ai.git
cd newsblog-ai
```

### 2. Set up a local dev environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn app.main:app --reload --port 8000
```

### 3. Create a branch

```bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/short-description
```

---

## Code style

- Python 3.12, fully typed (use `from __future__ import annotations` if needed for older compat)
- No bare `except:` — catch specific exceptions
- New modules follow the existing structure: provider → service → route
- No comments explaining *what* the code does — only *why* when it's non-obvious

---

## Submitting a pull request

1. Keep PRs focused — one feature or fix per PR
2. Update `.env.example` and `README.md` if you add new env vars or API fields
3. Make sure `docker compose up -d --build` still works
4. Open your PR against `main` with a clear description of what changed and why

---

## Reporting a bug

Use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) issue template and include the output of `docker logs newsblog-ai --tail 30`.

---

## License

By contributing you agree that your work will be licensed under the [MIT License](LICENSE).
