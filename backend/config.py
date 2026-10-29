"""Runtime settings for the Awaaz backend.

Plain dataclass read from the process environment, with `backend/.env` (and the
repo-root `.env`) loaded first via python-dotenv. Variables that already exist in
the environment always win, so tests can force an empty key.

DEMO_MODE semantics:
  on    never call an external provider; every AI call returns a fixture
  auto  call providers when a key is present; use fixtures if the key is
        missing or the call fails (default)
  off   never use fixtures; provider errors propagate
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

load_dotenv(dotenv_path=BACKEND_DIR / ".env", override=False)
load_dotenv(dotenv_path=REPO_DIR / ".env", override=False)


def _env(*names: str, default: str = "") -> str:
    """First non-empty value among the given env var names, else default."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


@dataclass(frozen=True)
class Settings:
    """All configuration in one place. Build with `load_settings()`."""

    # Sarvam (primary AI provider)
    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_llm_model: str = "sarvam-105b"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "ritu"
    sarvam_vision_model: str = "gemma4"

    # Paytm inference (secondary LLM, OpenAI-compatible)
    paytm_api_key: str = ""
    paytm_base_url: str = "https://api.inference.paytm.com"
    paytm_llm_model: str = "llama-3.3-70b-versatile"

    # xAI (vision fallback)
    xai_key: str = ""
    xai_base_url: str = "https://api.x.ai"
    xai_vision_model: str = "grok-4.3"

    # WhatsApp Cloud API
    wa_token: str = ""
    wa_phone_number_id: str = ""
    wa_verify_token: str = "awaaz-verify"
    wa_app_secret: str = ""

    # Merchant / hosting
    merchant_upi_vpa: str = "paytm.merchant@paytm"
    merchant_name: str = "Ramesh General Store"
    public_base_url: str = "http://localhost:8000"

    # Behaviour
    demo_mode: str = "auto"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'db.sqlite'}"
    cache_dir: Path = field(default_factory=lambda: BACKEND_DIR / ".cache")

    @property
    def has_sarvam(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def has_paytm(self) -> bool:
        return bool(self.paytm_api_key)

    @property
    def has_xai(self) -> bool:
        return bool(self.xai_key)

    @property
    def has_whatsapp(self) -> bool:
        return bool(self.wa_token and self.wa_phone_number_id)

    @property
    def fixtures_only(self) -> bool:
        """True when DEMO_MODE=on: no external call may be made."""
        return self.demo_mode == "on"

    @property
    def fixtures_allowed(self) -> bool:
        """True unless DEMO_MODE=off: fixtures may stand in for a failed call."""
        return self.demo_mode != "off"

    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
        if self.public_base_url and self.public_base_url not in origins:
            origins.append(self.public_base_url.rstrip("/"))
        return origins


def _normalise_demo_mode(raw: str) -> str:
    value = raw.strip().lower()
    if value in ("on", "true", "1", "yes"):
        return "on"
    if value in ("off", "false", "0", "no"):
        return "off"
    return "auto"


def load_settings() -> Settings:
    """Read settings from the environment (call again to pick up changes)."""
    return Settings(
        sarvam_api_key=_env("SARVAM_API_KEY"),
        sarvam_base_url=_env("SARVAM_API_BASE_URL", default="https://api.sarvam.ai").rstrip("/"),
        sarvam_stt_model=_env("SARVAM_STT_MODEL", default="saaras:v4"),
        sarvam_llm_model=_env("SARVAM_LLM_MODEL", default="sarvam-105b"),
        sarvam_tts_model=_env("SARVAM_TTS_MODEL", default="bulbul:v3"),
        sarvam_tts_speaker=_env("SARVAM_TTS_SPEAKER", default="ritu"),
        sarvam_vision_model=_env("SARVAM_VISION_MODEL", default="gemma4"),
        paytm_api_key=_env("PAYTM_API_KEY", "PAYTM_AI_KEY"),
        paytm_base_url=_env("PAYTM_API_BASE_URL", "PAYTM_AI_URL",
                            default="https://api.inference.paytm.com").rstrip("/"),
        paytm_llm_model=_env("PAYTM_LLM_MODEL", default="llama-3.3-70b-versatile"),
        xai_key=_env("XAI_KEY"),
        wa_token=_env("WA_TOKEN"),
        wa_phone_number_id=_env("WA_PHONE_NUMBER_ID"),
        wa_verify_token=_env("WA_VERIFY_TOKEN", default="awaaz-verify"),
        wa_app_secret=_env("WA_APP_SECRET"),
        merchant_upi_vpa=_env("MERCHANT_UPI_VPA", default="paytm.merchant@paytm"),
        merchant_name=_env("MERCHANT_NAME", default="Ramesh General Store"),
        public_base_url=_env("PUBLIC_BASE_URL", default="http://localhost:8000").rstrip("/"),
        demo_mode=_normalise_demo_mode(_env("DEMO_MODE", default="auto")),
        database_url=_env("DATABASE_URL", default=f"sqlite:///{BACKEND_DIR / 'db.sqlite'}"),
    )


settings = load_settings()
