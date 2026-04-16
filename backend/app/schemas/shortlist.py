import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShortlistCreate(BaseModel):
    jurisdiction_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    filters: dict = Field(default_factory=dict)
    parcel_ids: list[int] = Field(default_factory=list)


class ShortlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    jurisdiction_id: uuid.UUID
    name: str
    filters: dict
    parcel_ids: list[int]
    created_at: datetime
    updated_at: datetime
