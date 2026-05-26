from datetime import datetime
from pydantic import BaseModel, Field


class AttachmentMetadata(BaseModel):
    id: str
    name: str
    content_type: str = Field(alias="contentType")
    size: int


class Attachment(BaseModel):
    id: str
    name: str
    content_type: str = Field(alias="contentType")
    size: int
    content: bytes | None = None

    class Config:
        arbitrary_types_allowed = True


class Email(BaseModel):
    id: str
    message_id: str = Field(alias="internetMessageId")
    subject: str
    from_address: str = Field(alias="from")
    received_datetime: datetime = Field(alias="receivedDateTime")
    body_preview: str = Field(alias="bodyPreview", default="")
    attachments: list[AttachmentMetadata] = []

    class Config:
        populate_by_name = True
