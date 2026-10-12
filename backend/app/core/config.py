import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    demo_mode: bool
    data_dir: Path
    syslog_udp_port: int
    ollama_url: str
    ollama_model: str
    llm_timeout_s: float
    seal_batch_size: int
    seal_max_age_s: float
    seal_max_age_scripted_scn_s: float
    silence_min_seconds: float
    display_tz: str
    source_tz_default: str
    syslog_bind_host: str = "0.0.0.0"
    auth_file: Path | None = None
    auth_required: bool = False
    public_origin: str = ""


def load(env=os.environ) -> Config:
    demo = env.get("ANVAYA_DEMO_MODE", "0") == "1"
    return Config(
        demo_mode=demo,
        data_dir=Path(env.get("ANVAYA_DATA_DIR", "/data")),
        syslog_udp_port=int(env.get("ANVAYA_SYSLOG_UDP_PORT", "5514")),
        ollama_url=env.get("OLLAMA_URL", "http://ollama:11434"),
        ollama_model=env.get("OLLAMA_MODEL", "qwen2.5:3b"),
        llm_timeout_s=float(env.get("LLM_TIMEOUT_S", "5" if demo else "15")),
        seal_batch_size=int(env.get("SEAL_BATCH_SIZE", "16")),
        seal_max_age_s=float(env.get("SEAL_MAX_AGE_S", "5")),
        seal_max_age_scripted_scn_s=float(env.get("SEAL_MAX_AGE_SCRIPTED_SCN_S", "300")),
        silence_min_seconds=float(env.get("SILENCE_MIN_SECONDS", "15" if demo else "60")),
        display_tz=env.get("DISPLAY_TZ", "Asia/Kolkata"),
        source_tz_default=env.get("SOURCE_TZ_DEFAULT", "Asia/Kolkata"),
        syslog_bind_host=env.get("ANVAYA_SYSLOG_BIND_HOST", "0.0.0.0"),
        auth_file=Path(env["ANVAYA_AUTH_FILE"]) if env.get("ANVAYA_AUTH_FILE") else None,
        auth_required=env.get("ANVAYA_AUTH_REQUIRED", "0") == "1",
        public_origin=env.get("ANVAYA_PUBLIC_ORIGIN", "").rstrip("/"),
    )
