from hashlib import sha256
import json
class CatalogError(RuntimeError): pass
def ingest_catalog(raw:bytes,signature:str,publisher:str,trusted_publishers:set[str],verify_signature):
    if publisher not in trusted_publishers or not verify_signature(publisher,raw,signature): raise CatalogError("catalog signature is not trusted")
    data=json.loads(raw); out=[]
    for row in data.get("plugins",[]):
        if not isinstance(row.get("sha256"),str) or len(row["sha256"])!=64: raise CatalogError("package digest required")
        if not str(row.get("url","")).startswith("https://"): raise CatalogError("HTTPS package URL required")
        out.append({k:row[k] for k in ("name","version","url","sha256")})
    return {"publisher":publisher,"digest":sha256(raw).hexdigest(),"plugins":out}
