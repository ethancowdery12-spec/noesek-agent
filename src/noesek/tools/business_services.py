"""Thin, fixed-operation clients for five self-hostable business services.

Owner-requested (YouTube batch): Firecrawl, Twenty CRM, Chatwoot,
Activepieces and an e-signature service. No upstream code is copied or
vendored (Firecrawl, Twenty and Documenso are AGPL-3.0; Chatwoot and
Activepieces are MIT-core with enterprise directories), we only speak their
documented HTTP APIs, so nothing here inherits those licenses.

Safety shape:
- Operations are a fixed table; callers cannot pick arbitrary paths.
- Reads except Firecrawl scrape. Nothing creates, edits, sends or signs.
- Config comes from env vars NOESEK_<SERVICE>_BASE_URL / _TOKEN (and
  NOESEK_CHATWOOT_ACCOUNT_ID); tokens never appear in output or errors.
- Hosted Firecrawl (api.firecrawl.dev) spends credits, so it is refused unless
  NOESEK_FIRECRAWL_ALLOW_PAID=1 is set by the owner after the cost is approved.
- Signing: the YouTube transcript said "Document 360"; Documenso is only the
  closest researched candidate, identity unconfirmed. Documenso API paths are
  taken from its docs in the cloned repo.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

SERVICES: dict[str, dict] = {
    "firecrawl": {"ops": {"scrape": ("POST", "/v2/scrape")},
                  "auth": "bearer", "license": "AGPL-3.0 (on-disk LICENSE); API client only",
                  "source": "https://github.com/firecrawl/firecrawl",
                  "note": "Hosted API spends credits; self-host is free software but you run the infrastructure."},
    "twenty": {"ops": {"people_list": ("GET", "/rest/people"), "companies_list": ("GET", "/rest/companies")},
               "auth": "bearer", "license": "AGPL-3.0 mostly (on-disk LICENSE)",
               "source": "https://github.com/twentyhq/twenty"},
    "chatwoot": {"ops": {"conversations_list": ("GET", "/api/v1/accounts/{account_id}/conversations")},
                 "auth": "api_access_token", "license": "MIT core, enterprise dirs excluded (on-disk LICENSE)",
                 "source": "https://github.com/chatwoot/chatwoot"},
    "activepieces": {"ops": {"flows_list": ("GET", "/api/v1/flows")},
                     "auth": "bearer", "license": "MIT core, enterprise parts excluded (on-disk LICENSE)",
                     "source": "https://github.com/activepieces/activepieces",
                     "note": "Docs say API keys exist only on Platform/Enterprise editions (paid)."},
    "signing": {"ops": {"templates_list": ("GET", "/api/v2/template")},
                "auth": "raw", "license": "Documenso: AGPL-3.0 (on-disk LICENSE)",
                "source": "https://github.com/documenso/documenso",
                "note": "Transcript said 'Document 360'; Documenso is a candidate, not a confirmed match."},
}
_ENV = {"signing": "SIGNING"}


class BusinessServiceInput(BaseModel):
    action: str = Field(description="list | call")
    service: str = Field(default="", description="firecrawl | twenty | chatwoot | activepieces | signing")
    op: str = Field(default="", description="call: operation name from list")
    url: str = Field(default="", max_length=2000, description="firecrawl scrape: page URL")
    limit: int = Field(default=20, ge=1, le=100, description="list operations: page size")


def _env(service: str, key: str) -> str:
    return os.environ.get(f"NOESEK_{_ENV.get(service, service.upper())}_{key}", "").strip()


def _base_ok(base: str) -> bool:
    u = urlparse(base)
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1"})


def _headers(auth: str, token: str) -> dict:
    return {"bearer": {"Authorization": f"Bearer {token}"},
            "api_access_token": {"api_access_token": token},
            "raw": {"Authorization": token}}[auth]


def describe() -> dict:
    return {"services": {k: {"ops": sorted(v["ops"]), "license": v["license"], "source": v["source"],
                             "note": v.get("note", ""),
                             "configured": bool(_env(k, "BASE_URL") and _env(k, "TOKEN"))}
                         for k, v in SERVICES.items()}}


async def business_services(inp: BusinessServiceInput) -> dict:
    a = inp.action.strip().lower()
    if a == "list":
        return describe()
    if a != "call":
        return {"error": f"unknown action '{inp.action}'", "actions": ["list", "call"]}
    svc = SERVICES.get(inp.service.strip().lower())
    name = inp.service.strip().lower()
    if not svc:
        return {"error": f"unknown service '{inp.service}'", "services": sorted(SERVICES)}
    op = svc["ops"].get(inp.op.strip())
    if not op:
        return {"error": f"unknown op '{inp.op}'", "ops": sorted(svc["ops"])}
    base, token = _env(name, "BASE_URL").rstrip("/"), _env(name, "TOKEN")
    if not base or not token:
        return {"error": f"{name} is not configured",
                "setup": f"set NOESEK_{_ENV.get(name, name.upper())}_BASE_URL and _TOKEN (token stays server-side)"}
    if not _base_ok(base):
        return {"error": "base URL must be https (http only for localhost)"}
    if name == "firecrawl" and urlparse(base).hostname == "api.firecrawl.dev" \
            and os.environ.get("NOESEK_FIRECRAWL_ALLOW_PAID") != "1":
        return {"error": "hosted Firecrawl spends credits; owner approval of the cost is required "
                         "(set NOESEK_FIRECRAWL_ALLOW_PAID=1 after approving) or point at a self-hosted base URL"}
    method, path = op
    body, params = None, None
    if name == "firecrawl":
        if urlparse(inp.url).scheme not in {"http", "https"}:
            return {"error": "url must be http(s)"}
        body = {"url": inp.url, "formats": ["markdown"]}
    else:
        params = {"limit": inp.limit} if name in {"twenty", "activepieces"} else None
    if "{account_id}" in path:
        acct = _env(name, "ACCOUNT_ID")
        if not acct.isdigit():
            return {"error": "set NOESEK_CHATWOOT_ACCOUNT_ID to the numeric account id"}
        path = path.format(account_id=acct)
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.request(method, base + path, headers=_headers(svc["auth"], token),
                                json=body, params=params)
        if r.status_code in (401, 403):
            return {"error": f"{name} rejected the token (HTTP {r.status_code})"}
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"{name} request failed (HTTP {e.response.status_code})"}
    except (httpx.HTTPError, ValueError) as e:
        return {"error": f"{name} request failed: {type(e).__name__}"}
    text = str(data)
    return {"service": name, "op": inp.op.strip(), "data": data if len(text) <= 20000 else {"truncated": text[:20000]}}
