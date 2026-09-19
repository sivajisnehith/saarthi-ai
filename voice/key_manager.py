import logging
import os
import threading
from typing import List, Optional

logger = logging.getLogger("saarthi.voice.key_manager")


class SarvamKeyManager:
    """
    Thread-safe and async-safe key pool manager for Sarvam AI API keys.
    Provides automatic fallback / failover when credits run out, quotas are exceeded,
    or authentication/payment errors occur (HTTP 401, 402, 403, 429).
    Supports cyclical rotation across all configured keys.
    """

    def __init__(self, keys: Optional[List[str]] = None):
        self._lock = threading.Lock()
        if keys:
            self._keys = [k.strip() for k in keys if k and k.strip()]
        else:
            self._keys = self._load_keys_from_env()

        if not self._keys:
            raise RuntimeError(
                "No Sarvam API keys configured! Please set SARVAM_API_KEY, SARVAM_FALLBACK_API_KEYS, or SARVAM_API_KEYS."
            )

        self._current_index = 0
        logger.info(
            "Initialized SarvamKeyManager with %d key(s). Active key: #%d (%s)",
            len(self._keys),
            self._current_index + 1,
            self.mask_key(self._keys[0]),
        )

    @classmethod
    def _load_keys_from_env(cls) -> List[str]:
        raw_keys: List[str] = []

        # 1. Check SARVAM_API_KEYS (comma-separated list)
        env_keys = os.getenv("SARVAM_API_KEYS", "")
        if env_keys:
            for k in env_keys.split(","):
                k = k.strip()
                if k and k not in raw_keys:
                    raw_keys.append(k)

        # 2. Check primary SARVAM_API_KEY
        primary = os.getenv("SARVAM_API_KEY", "").strip()
        if primary and primary not in raw_keys:
            raw_keys.insert(0, primary)

        # 3. Check SARVAM_FALLBACK_API_KEYS (comma-separated list)
        fallbacks = os.getenv("SARVAM_FALLBACK_API_KEYS", "")
        if fallbacks:
            for k in fallbacks.split(","):
                k = k.strip()
                if k and k not in raw_keys:
                    raw_keys.append(k)

        return raw_keys

    @staticmethod
    def mask_key(key: str) -> str:
        """Returns a safely masked representation of an API key."""
        if not key or len(key) <= 10:
            return "sk_***"
        return f"{key[:6]}...{key[-4:]}"

    def get_current_key(self) -> str:
        """Returns the currently active Sarvam API key."""
        with self._lock:
            return self._keys[self._current_index]

    def get_current_index(self) -> int:
        """Returns the 0-based index of the currently active key."""
        with self._lock:
            return self._current_index

    def get_all_keys(self) -> List[str]:
        """Returns a copy of all configured keys in rotation."""
        with self._lock:
            return list(self._keys)

    def mark_key_exhausted(self, failed_key: str, reason: str = "") -> str:
        """
        Marks a specific key as exhausted / failed and rotates to the next key.
        If another concurrent task already rotated away from failed_key, avoids double-skipping.
        Returns the new active key.
        """
        with self._lock:
            current_key = self._keys[self._current_index]
            if current_key == failed_key:
                old_idx = self._current_index
                self._current_index = (self._current_index + 1) % len(self._keys)
                new_key = self._keys[self._current_index]
                logger.warning(
                    "Sarvam API key #%d (%s) exhausted/failed (%s). "
                    "Rotating to fallback key #%d (%s) [Pool size: %d]",
                    old_idx + 1,
                    self.mask_key(failed_key),
                    reason or "credit/quota limit reached",
                    self._current_index + 1,
                    self.mask_key(new_key),
                    len(self._keys),
                )
                return new_key
            else:
                # Key was already rotated by another concurrent call
                new_key = self._keys[self._current_index]
                logger.info(
                    "Sarvam API key (%s) was already rotated to key #%d (%s)",
                    self.mask_key(failed_key),
                    self._current_index + 1,
                    self.mask_key(new_key),
                )
                return new_key


# Global shared singleton instance
sarvam_key_manager = SarvamKeyManager()
