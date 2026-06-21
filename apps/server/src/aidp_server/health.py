from typing import Literal, TypedDict

from fastapi import APIRouter


class HealthResponse(TypedDict):
    status: Literal["ok"]
    service: str


router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> HealthResponse:
    return {"status": "ok", "service": "aidp-server"}
