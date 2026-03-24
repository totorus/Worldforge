from fastapi import APIRouter

router = APIRouter()


@router.post("/{world_id}/bookstack")
async def export_to_bookstack(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/bookstack/status")
async def export_status(world_id: str):
    return {"message": "TODO"}


@router.post("/{world_id}/bookstack/sync")
async def sync_bookstack(world_id: str):
    return {"message": "TODO"}
