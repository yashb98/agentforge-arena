# Golden reference — `url-shortener-saas`

Minimal FastAPI app that passes `challenges/library/url-shortener-saas/hidden_tests/`.

Used to prove hidden tests are runnable and aligned with the challenge. Tournament teams are **not** required to match this implementation.

Hidden tests read `AGENTFORGE_HIDDEN_TEST_BASE_URL` (default `http://localhost:8000`). The golden runner sets this automatically when using an ephemeral port.

## Run locally

```bash
cd challenges/fixtures/url-shortener-saas/golden
pip install -r requirements.txt pytest pytest-asyncio
uvicorn main:app --host 127.0.0.1 --port 8000
# other terminal, from repo root:
AGENTFORGE_HIDDEN_TEST_BASE_URL=http://127.0.0.1:8000 pytest challenges/library/url-shortener-saas/hidden_tests \
  --rootdir=challenges/fixtures/url-shortener-saas/golden \
  -q --override-ini="addopts="
```

Or: `make golden-hidden-url-shortener` from the monorepo root.
