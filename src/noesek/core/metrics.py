from collections import Counter

COUNTERS: Counter[str] = Counter()

def inc(name: str, amount: int = 1):
    COUNTERS[name] += amount

def snapshot() -> dict[str, int]:
    return dict(COUNTERS)

def render_prometheus() -> str:
    lines = []
    for name in sorted(COUNTERS):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {COUNTERS[name]}")
    return "\n".join(lines) + ("\n" if lines else "")
