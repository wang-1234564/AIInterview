"""数据库中敏感字段（API Key）的加密与解密。

密钥来源，按优先级：
1. 环境变量 `APP_SECRET_KEY`
2. 项目根目录的 `.secret_key` 文件（首次运行自动生成，已在 .gitignore 中）

注意：删除或更换密钥后，已保存的 API Key 将无法解密（会视为“未配置”），
需要重新填写。
"""
import base64
import hashlib
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import BASE_DIR, settings

_KEY_FILE = BASE_DIR / ".secret_key"


def _load_secret() -> str:
    if settings.app_secret_key:
        return settings.app_secret_key
    if _KEY_FILE.exists():
        value = _KEY_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    _KEY_FILE.write_text(value, encoding="utf-8")
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass  # Windows 上可能不支持
    return value


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(_load_secret().encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt(plain: str) -> str:
    """加密明文；空串原样返回（表示未配置）。"""
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """解密；不是密文或解密失败时返回空串。"""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return ""


def is_encrypted(token: str) -> bool:
    """判断是否为可解密的密文（用于把历史明文迁移为密文）。"""
    if not token:
        return False
    try:
        _fernet().decrypt(token.encode("ascii"))
        return True
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return False
