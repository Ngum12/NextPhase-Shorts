from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str

class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    style: str
    desired_seconds: int
    source_duration_seconds: float
    output_duration_seconds: float | None
    status: str
    error_code: str | None
    attempt_count: int
    created_at: datetime
    finished_at: datetime | None

class StyleInfo(BaseModel):
    id: str
    name: str
    description: str
    available: bool
