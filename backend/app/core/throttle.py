import time
from collections import defaultdict, deque
from threading import Lock

# In-process login throttle.
#
# LIMITATION, stated plainly: this lives in one worker's memory. Run several
# uvicorn workers and each keeps its own counters, so the effective limit
# multiplies by the worker count; restart the process and it resets. It raises
# the cost of online guessing against a single-worker deployment and nothing
# more.
#
# It is NOT a substitute for rate limiting at the reverse proxy, which is where
# this belongs in production. It is here because the legacy application allowed
# unlimited login attempts against unsalted MD5, and some resistance while the
# rebuild is in progress beats none.


class LoginThrottle:
    def __init__(self, max_attempts: int = 10, window_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = now - self.window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        """Called on success, so a legitimate user who mistyped a few times is
        not locked out by their own correction."""
        with self._lock:
            self._attempts.pop(key, None)


login_throttle = LoginThrottle()
