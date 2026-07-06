from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_hasher = PasswordHasher()


def hash_secret(secret: str) -> str:
    return _hasher.hash(secret)


class LockedOut(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"locked out, retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass
class _Bucket:
    failures: int = 0
    locked_until: float = 0.0


class SecretGate:
    def __init__(
        self,
        secret_hash: str,
        max_attempts: int,
        lockout_seconds: int,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._secret_hash = secret_hash
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._now = now
        self._buckets: dict[str, _Bucket] = {}

    def verify(self, client_key: str, candidate: str) -> bool:
        bucket = self._buckets.setdefault(client_key, _Bucket())
        now = self._now()

        if bucket.locked_until > now:
            raise LockedOut(retry_after=int(bucket.locked_until - now))

        try:
            _hasher.verify(self._secret_hash, candidate)
        except (VerifyMismatchError, VerificationError):
            bucket.failures += 1
            if bucket.failures >= self._max_attempts:
                bucket.locked_until = now + self._lockout_seconds
            return False

        bucket.failures = 0
        bucket.locked_until = 0.0
        return True
