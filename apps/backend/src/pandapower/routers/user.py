from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["user"])


class UserResponse(BaseModel):
    email: str
    role: str = "user"


@router.get("/me", response_model=UserResponse)
async def get_me() -> UserResponse:
    """Get current user profile."""
    return UserResponse(
        email="admin@test.com",
        role="admin",
    )
