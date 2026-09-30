"""Configuração centralizada da PoV, sem dependências adicionais."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


BACKEND_DIR = Path(__file__).resolve().parent


def _path_env(name: str, default: str = "") -> str:
    """Caminho do .env, ancorado em backend/.

    Um caminho relativo resolveria contra o cwd, e os scripts desta PoV rodam da
    raiz do repositório enquanto o uvicorn roda de backend/ — o mesmo .env
    apontaria para dois arquivos diferentes, e o segundo não existe.
    """
    bruto = os.getenv(name, default).strip()
    if not bruto:
        return ""
    caminho = Path(bruto).expanduser()
    if not caminho.is_absolute():
        caminho = BACKEND_DIR / caminho
    return str(caminho)


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = os.getenv("MONGO_URI", "").strip()
    mongo_db: str = os.getenv("QE_DB", "cofre").strip() or "cofre"
    mongo_timeout_ms: int = _int_env("MONGO_TIMEOUT_MS", 8_000, 100, 300_000)

    # Cofre e criptografia
    key_vault_ns: str = os.getenv("QE_KEY_VAULT_NS", "cofre.__keyVault").strip() or "cofre.__keyVault"
    kms_provider: str = (os.getenv("QE_KMS_PROVIDER", "local").strip().lower() or "local")
    local_master_key_path: str = _path_env("QE_LOCAL_MASTER_KEY_PATH")
    crypt_shared_path: str = _path_env("CRYPT_SHARED_PATH")

    # AWS KMS (somente no modo aws)
    aws_kms_key_arn: str = os.getenv("AWS_KMS_KEY_ARN", "").strip()
    aws_kms_region: str = os.getenv("AWS_KMS_REGION", "sa-east-1").strip()
    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()

    # Ajustes da demo
    contention_factor: int = _int_env("QE_CONTENTION_FACTOR", 8, 0, 64)

    # Guardas
    demo_admin_token: str = os.getenv("DEMO_ADMIN_TOKEN", "").strip()
    allowed_origins: tuple[str, ...] = _csv_env(
        "ALLOWED_ORIGINS",
        "http://localhost:5300,http://127.0.0.1:5300",
    )
    max_request_bytes: int = _int_env("MAX_REQUEST_BYTES", 1_048_576, 1, 104_857_600)

    @property
    def crypt_shared_disponivel(self) -> bool:
        return bool(self.crypt_shared_path) and Path(self.crypt_shared_path).exists()

    @property
    def aws_configurado(self) -> bool:
        return all((self.aws_kms_key_arn, self.aws_access_key_id, self.aws_secret_access_key))

    @property
    def kms_configurado(self) -> bool:
        """O provedor ativo tem tudo o que precisa para abrir uma DEK."""
        if self.kms_provider == "aws":
            return self.aws_configurado
        return bool(self.local_master_key_path) and Path(self.local_master_key_path).exists()

    @property
    def qe_configured(self) -> bool:
        """Auto-encryption é possível. Sem isso os módulos 02–06 degradam."""
        return bool(self.mongo_uri) and self.crypt_shared_disponivel and self.kms_configurado


settings = Settings()
