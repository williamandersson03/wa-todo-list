from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


password_hasher = PasswordHasher()


@dataclass
class LoginRateLimiter:
    attempts: int
    window_seconds: int

    def __post_init__(self) -> None:
        self.store: dict[str, deque[float]] = defaultdict(deque)

    def is_blocked(self, key: str) -> bool:
        now = time.time()
        queue = self.store[key]
        while queue and now - queue[0] > self.window_seconds:
            queue.popleft()
        return len(queue) >= self.attempts

    def add_failure(self, key: str) -> None:
        self.store[key].append(time.time())

    def clear(self, key: str) -> None:
        self.store.pop(key, None)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def new_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
