from fastapi import APIRouter

router = APIRouter()


@router.post("/start")
async def start_wizard():
    return {"message": "TODO"}


@router.post("/{session_id}/message")
async def send_message(session_id: str):
    return {"message": "TODO"}


@router.get("/{session_id}/history")
async def get_history(session_id: str):
    return {"message": "TODO"}


@router.post("/{session_id}/finalize")
async def finalize(session_id: str):
    return {"message": "TODO"}


@router.post("/{session_id}/validate")
async def validate(session_id: str):
    return {"message": "TODO"}
