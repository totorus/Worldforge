from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_worlds():
    return {"message": "TODO"}


@router.get("/{world_id}")
async def get_world(world_id: str):
    return {"message": "TODO"}


@router.put("/{world_id}/config")
async def update_config(world_id: str):
    return {"message": "TODO"}


@router.delete("/{world_id}")
async def delete_world(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/timeline")
async def get_timeline(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/narrative")
async def get_narrative(world_id: str):
    return {"message": "TODO"}
