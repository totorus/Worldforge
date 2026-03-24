from fastapi import APIRouter

router = APIRouter()


@router.post("/{world_id}")
async def run_narration(world_id: str):
    return {"message": "TODO"}


@router.post("/{world_id}/partial")
async def run_partial_narration(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/status")
async def narration_status(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/blocks")
async def get_narrative_blocks(world_id: str):
    return {"message": "TODO"}
