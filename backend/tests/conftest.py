"""Test setup: isolated temp database, no provider keys, fixtures-only mode.

The env vars are set BEFORE any app module is imported so that a developer's real
backend/.env keys can never be used by the test suite.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="awaaz-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.sqlite"
os.environ["CACHE_DIR"] = f"{_TMP}/cache"  # audio cached by a real run must not change test results
for _k in ("SARVAM_API_KEY", "OPENROUTER_API_KEY", "WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_APP_SECRET",
           "SARVAM_STT_MODEL", "SARVAM_STT_MODE", "SARVAM_TTS_MODEL", "SARVAM_TTS_SPEAKER", "SARVAM_LLM_MODEL"):
    os.environ[_k] = ""  # a developer's .env must not change the defaults under test
os.environ["DEMO_MODE"] = "on"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8000"

import pytest  # noqa: E402

import seed as seed_module  # noqa: E402
from database import SessionLocal  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded():
    seed_module.seed(reset=True, verbose=False)
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
