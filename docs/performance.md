# Performance Notes

## Phase 7 Measurement

Date measured: **February 22, 2026**

Hotspot targeted: queue operations in custom URL crawler.

### Benchmark command

```bash
python3 tools/benchmark_queue.py
```

### Result

- `list.pop(0)`: **0.2746s**
- `deque.popleft()`: **0.0127s**
- Speedup: **21.59x**

## Change applied

The custom crawler now uses `collections.deque` (`popleft`) for BFS queue management instead of list front pops.

Rationale: list front pops are O(n), while deque front pops are O(1).
