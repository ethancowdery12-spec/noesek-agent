from dataclasses import dataclass
from hashlib import sha256
@dataclass(frozen=True)
class MediaPolicy:
 allowed_types:frozenset[str]; max_bytes:int=25_000_000
async def ingest_media(data:bytes,content_type:str,policy:MediaPolicy,scanner,processor):
 if content_type not in policy.allowed_types: raise ValueError("media type is not allowed")
 if len(data)>policy.max_bytes: raise ValueError("media exceeds size limit")
 digest=sha256(data).hexdigest()
 if not await scanner.clean(data,content_type): raise PermissionError("media scanner rejected content")
 result=await processor.process(data,content_type)
 return {"sha256":digest,"bytes":len(data),"content_type":content_type,"result":result}
