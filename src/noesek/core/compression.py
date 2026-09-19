"""Deterministic context compaction that preserves the current turn and tool pairs."""
import json

def estimate_chars(messages: list[dict]) -> int:
    return sum(len(json.dumps(m,ensure_ascii=False,separators=(",",":"))) for m in messages)

def compact(messages: list[dict], budget: int) -> tuple[list[dict],dict]:
    if budget < 256: raise ValueError("budget too small")
    if estimate_chars(messages)<=budget: return list(messages),{"removed":0,"chars":estimate_chars(messages)}
    systems=[m for m in messages if m.get("role")=="system"][:1]
    tail=[]; used=estimate_chars(systems)
    for m in reversed(messages):
        if m in systems: continue
        size=estimate_chars([m])
        if used+size>budget and tail: break
        if size>budget-used:
            if not tail and m.get("role") in {"user","assistant"}:
                item=dict(m); item["content"]=str(item.get("content",""))[-max(1,budget-used-100):]; tail.append(item)
            break
        tail.append(m); used+=size
    tail.reverse(); kept=systems+tail
    return kept,{"removed":max(0,len(messages)-len(kept)),"chars":estimate_chars(kept)}
