"""Micro-benchmark: BFS queue list.pop(0) vs collections.deque.popleft."""

from __future__ import annotations

import time
from collections import deque


def benchmark_list(size: int) -> float:
    queue = [(f"https://example.com/{i}", i % 3) for i in range(size)]
    started = time.perf_counter()
    while queue:
        queue.pop(0)
    return time.perf_counter() - started


def benchmark_deque(size: int) -> float:
    queue = deque((f"https://example.com/{i}", i % 3) for i in range(size))
    started = time.perf_counter()
    while queue:
        queue.popleft()
    return time.perf_counter() - started


def main() -> int:
    size = 50_000
    list_seconds = benchmark_list(size)
    deque_seconds = benchmark_deque(size)

    print(f"size={size}")
    print(f"list.pop(0): {list_seconds:.4f}s")
    print(f"deque.popleft(): {deque_seconds:.4f}s")
    print(f"speedup: {list_seconds / deque_seconds:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
