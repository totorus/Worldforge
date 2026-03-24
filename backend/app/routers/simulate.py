from fastapi import APIRouter

router = APIRouter()


@router.post("/{world_id}")
async def run_simulation(world_id: str):
    return {"message": "TODO"}


@router.post("/{world_id}/extend")
async def extend_simulation(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/status")
async def simulation_status(world_id: str):
    return {"message": "TODO"}


@router.get("/{world_id}/timeline")
async def get_timeline(world_id: str):
    return {"message": "TODO"}
