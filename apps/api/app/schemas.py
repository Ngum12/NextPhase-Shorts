from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(gt=0)
    refresh_token: str
    refresh_expires_in: int = Field(gt=0)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    email_verified_at: datetime | None
    email_verification_method: str | None

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
    preview_parent_id: str | None = None
    operation: Literal['render','preview','analysis']='render'

class StyleInfo(BaseModel):
    id: str
    name: str
    description: str
    available: bool
