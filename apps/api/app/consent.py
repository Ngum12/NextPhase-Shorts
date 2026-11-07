"""Versioned uploader attestation, not verification of ownership or legal clearance."""
from fastapi import HTTPException
from pydantic import BaseModel, StrictBool, field_validator
from typing import Literal

RIGHTS_VERSION='upload-rights-v1'
RIGHTS_TEXT=('This footage is mine or I have permission to upload and edit it, including '
             'permission from people shown or heard. I understand the video is uploaded for server processing.')


class RightsAcknowledgement(BaseModel):
    rights_confirmed: StrictBool
    consent_version: Literal['upload-rights-v1']

    @field_validator('rights_confirmed')
    @classmethod
    def affirmative(cls,value):
        if value is not True:raise ValueError('Explicit upload rights acknowledgement is required')
        return value


def require_rights(confirmed,version):
    if confirmed is not True or version!=RIGHTS_VERSION:
        raise HTTPException(422,'Confirm upload rights and server processing before uploading.')
