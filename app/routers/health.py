from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/", summary="Health check")
def health():
    return {"status": "ok"}
