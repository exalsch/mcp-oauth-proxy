from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

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
    last_seen: float = 0.0


class SecretGate:
    def __init__(
        self,
        secret_hash: str,
        max_attempts: int,
        lockout_seconds: int,
        now: Callable[[], float] = time.monotonic,
        max_buckets: int = 10_000,
    ) -> None:
        self._secret_hash = secret_hash
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._now = now
        self._max_buckets = max_buckets
        self._buckets: dict[str, _Bucket] = {}

    def _prune(self, now: float) -> None:
        # The bucket key is a client address; a hostile client can present many
        # distinct values, so an unbounded dict is a memory-exhaustion vector.
        # Drop buckets that are neither locked nor recently active (their state
        # would reset on next use anyway), preferring the least-recently seen.
        if len(self._buckets) <= self._max_buckets:
            return
        stale = [
            key
            for key, b in self._buckets.items()
            if b.locked_until <= now and now - b.last_seen >= self._lockout_seconds
        ]
        for key in stale:
            del self._buckets[key]
        if len(self._buckets) > self._max_buckets:
            evictable = sorted(
                (key for key, b in self._buckets.items() if b.locked_until <= now),
                key=lambda key: self._buckets[key].last_seen,
            )
            for key in evictable[: len(self._buckets) - self._max_buckets]:
                del self._buckets[key]

    def verify(self, client_key: str, candidate: str) -> bool:
        now = self._now()
        self._prune(now)
        bucket = self._buckets.setdefault(client_key, _Bucket())
        bucket.last_seen = now

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
