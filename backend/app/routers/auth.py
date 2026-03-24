from fastapi import APIRouter

router = APIRouter()


@router.post("/register")
async def register():
    return {"message": "TODO"}


@router.post("/login")
async def login():
    return {"message": "TODO"}


@router.post("/refresh")
async def refresh():
    return {"message": "TODO"}


@router.get("/me")
async def me():
    return {"message": "TODO"}
