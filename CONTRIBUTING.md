# Contributing to heard

Thanks for helping improve `heard`. Keep changes focused, testable, and safe to run on a Linux desktop.

## Code map

- `lib/heard.py` — transcription orchestration, worker pool, and audio conversion.
- `lib/heard_worker.py` — one worker process and its browser/upstream protocol.
- `scripts/` — desktop toggle and Hermes STT adapter.
- `tests/test_heard.py` — offline unit tests plus one explicitly opt-in live integration test.

Read the requirements, configuration, and known limitations in [`README.md`](README.md) before changing runtime behavior. The upstream endpoint is unofficial and can change; do not turn a live-network assumption into an unverified guarantee.

## Run the default test suite

Requirements: Python 3.12 or newer, `pytest`, and `ffmpeg` on `PATH`. The tests use a fake worker for the subprocess protocol and do not require Playwright, Chromium, credentials, or network access. The audio-conversion tests do invoke the local `ffmpeg` binary with synthetic audio.

```bash
python -m pytest tests/ -q
```

CI installs `ffmpeg` and `pytest`, then runs the same command. With `uv`, an isolated pytest environment is also supported:

```bash
uv run --with pytest python -m pytest tests/ -q
```

## Testing worker-protocol changes

Prefer the existing fake-worker pattern in `tests/test_heard.py`. Set `HEARD_WORKER_SCRIPT` to a temporary script that implements the newline-delimited JSON stdin/stdout protocol; tests should assert ready, success, and error responses without starting a browser or contacting the upstream. Keep tests deterministic and clean up subprocesses and temporary files.

## Live integration test (opt-in only)

The integration test contacts the configured upstream and needs Playwright plus its Chromium build. It is excluded from normal CI and the default test run. Run it only when you are authorized to use the endpoint and have confirmed its current terms and rate limits:

```bash
uv run --with pytest --with playwright playwright install chromium
HEARD_INTEGRATION=1 uv run --with pytest --with playwright python -m pytest tests/ -q -k integration
```

Do not add session cookies, credentials, recordings, or other private data to the repository, fixtures, logs, or test output. Do not make the live integration test a required CI check.

## Pull-request checklist

- Keep the change narrowly scoped and describe the user-visible reason.
- Add or update offline tests for behavior changes; avoid relying on live services.
- Run `python -m pytest tests/ -q` and report the actual result.
- Review the diff for recordings, session data, credentials, generated files, and unrelated changes before submitting.
- Update `README.md` when requirements, commands, configuration, or supported behavior change.
