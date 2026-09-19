"""OAuth device flow with an injected secret store. Tokens never appear in status results."""
import asyncio, time
from dataclasses import dataclass
from typing import Protocol
class SecretStore(Protocol):
    async def put(self,name:str,value:str)->None: ...
    async def exists(self,name:str)->bool: ...
@dataclass(frozen=True)
class DeviceAuthorization:
    device_code:str; user_code:str; verification_uri:str; expires_in:int; interval:int=5
class DeviceFlowError(RuntimeError): pass
async def complete_device_flow(auth:DeviceAuthorization,poll,store:SecretStore,secret_name:str,sleep=asyncio.sleep,clock=time.monotonic):
    if auth.expires_in<=0 or auth.interval<=0: raise ValueError("invalid device authorization")
    deadline=clock()+auth.expires_in; interval=auth.interval
    while clock()<deadline:
        result=await poll(auth.device_code)
        if "access_token" in result:
            await store.put(secret_name,result["access_token"])
            return {"connected":True,"secret_name":secret_name,"token_stored":True}
        error=result.get("error")
        if error=="slow_down": interval+=5
        elif error not in {"authorization_pending",None}: raise DeviceFlowError(error)
        await sleep(interval)
    raise DeviceFlowError("expired_token")
async def auth_status(store:SecretStore,secret_name:str): return {"connected":await store.exists(secret_name),"secret_name":secret_name}
