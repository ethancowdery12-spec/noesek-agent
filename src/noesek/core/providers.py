"""Native provider wire adapters with one normalized Noesek response shape."""
import json
from abc import ABC, abstractmethod
import httpx
from .types import LLMReply, ToolCall
from .llm import LLMError, _llm_error

class ProviderError(RuntimeError): pass

class ProviderAdapter(ABC):
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float=90):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url.rstrip("/"), timeout
    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...

class AnthropicAdapter(ProviderAdapter):
    async def complete(self, messages, tools):
        system="\n\n".join(m.get("content","") for m in messages if m.get("role")=="system")
        converted=[m for m in messages if m.get("role") in {"user","assistant"}]
        body={"model":self.model,"max_tokens":4096,"messages":converted}
        if system: body["system"]=system
        if tools:
            body["tools"]=[{"name":t["function"]["name"],"description":t["function"].get("description",""),"input_schema":t["function"]["parameters"]} for t in tools]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r=await client.post(self.base_url+"/messages",json=body,headers={"x-api-key":self.api_key,"anthropic-version":"2023-06-01"})
        if r.status_code >= 400: raise _llm_error(self.base_url, self.model, r.status_code, "HTTP error", "anthropic")
        data=r.json(); text=[]; calls=[]
        for block in data.get("content",[]):
            if block.get("type")=="text": text.append(block.get("text",""))
            elif block.get("type")=="tool_use": calls.append(ToolCall(id=block["id"],name=block["name"],arguments=block.get("input") or {}))
        return LLMReply(content="".join(text) or None,tool_calls=calls)

class GeminiAdapter(ProviderAdapter):
    async def complete(self, messages, tools):
        contents=[]
        for m in messages:
            if m.get("role")=="system": continue
            contents.append({"role":"model" if m.get("role")=="assistant" else "user","parts":[{"text":m.get("content","")} ]})
        body={"contents":contents}
        systems=[m.get("content","") for m in messages if m.get("role")=="system"]
        if systems: body["systemInstruction"]={"parts":[{"text":"\n\n".join(systems)}]}
        if tools:
            body["tools"]=[{"functionDeclarations":[{"name":t["function"]["name"],"description":t["function"].get("description",""),"parameters":t["function"]["parameters"]} for t in tools]}]
        url=f"{self.base_url}/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=self.timeout) as client: r=await client.post(url,params={"key":self.api_key},json=body)
        if r.status_code >= 400: raise _llm_error(self.base_url, self.model, r.status_code, "HTTP error", "gemini")
        parts=((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts",[]); text=[]; calls=[]
        for i,p in enumerate(parts):
            if "text" in p: text.append(p["text"])
            if "functionCall" in p:
                c=p["functionCall"]; calls.append(ToolCall(id=f"gemini-{i}",name=c["name"],arguments=c.get("args") or {}))
        return LLMReply(content="".join(text) or None,tool_calls=calls)

class FailoverLLM:
    """Try providers only on transport/rate/server failure, never auth or bad requests."""
    def __init__(self, adapters: list[ProviderAdapter]):
        if not adapters: raise ValueError("at least one provider is required")
        self.adapters=adapters
    async def complete(self,messages,tools):
        errors=[]
        for adapter in self.adapters:
            try: return await adapter.complete(messages,tools)
            except (httpx.TransportError, httpx.TimeoutException, ProviderError) as e:
                text=str(e); errors.append(text)
                if "HTTP 4" in text and "HTTP 429" not in text: raise
        raise ProviderError("all providers failed: "+"; ".join(errors))

class BedrockAdapter:
    """Bedrock Converse adapter. AWS credential resolution belongs to the injected SDK client."""
    def __init__(self, client, model: str): self.client,self.model=client,model
    async def complete(self,messages,tools):
        import asyncio
        system=[{"text":m.get("content","")} for m in messages if m.get("role")=="system"]
        wire=[{"role":m["role"],"content":[{"text":m.get("content","")}]} for m in messages if m.get("role") in {"user","assistant"}]
        kwargs={"modelId":self.model,"messages":wire}
        if system: kwargs["system"]=system
        if tools: kwargs["toolConfig"]={"tools":[{"toolSpec":{"name":t["function"]["name"],"description":t["function"].get("description","") or "No description","inputSchema":{"json":t["function"]["parameters"]}}} for t in tools]}
        data=await asyncio.to_thread(self.client.converse,**kwargs); blocks=(data.get("output",{}).get("message",{}).get("content",[])); text=[]; calls=[]
        for b in blocks:
            if "text" in b: text.append(b["text"])
            if "toolUse" in b:
                c=b["toolUse"]; calls.append(ToolCall(id=c["toolUseId"],name=c["name"],arguments=c.get("input") or {}))
        return LLMReply(content="".join(text) or None,tool_calls=calls)
