from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class StreamEvent:
    type:str; text:str=""; tool_name:str=""; tool_id:str=""; arguments:dict|None=None
def normalize_stream(provider:str,event:dict)->list[dict]:
    out=[]; p=provider.lower()
    if p=="openai":
        for c in event.get("choices",[]):
            d=c.get("delta",{});
            if d.get("content"): out.append(StreamEvent("text.delta",text=d["content"]))
            for t in d.get("tool_calls",[]): out.append(StreamEvent("tool.delta",tool_name=t.get("function",{}).get("name","") ,tool_id=t.get("id","") ,arguments={"json_fragment":t.get("function",{}).get("arguments","")}))
    elif p=="anthropic":
        if event.get("type")=="content_block_delta" and event.get("delta",{}).get("type")=="text_delta": out.append(StreamEvent("text.delta",text=event["delta"].get("text","")))
    elif p in {"gemini","google"}:
        for c in event.get("candidates",[]):
            for part in c.get("content",{}).get("parts",[]):
                if part.get("text"): out.append(StreamEvent("text.delta",text=part["text"]))
    else: raise ValueError("unknown stream provider")
    return [asdict(x) for x in out]
