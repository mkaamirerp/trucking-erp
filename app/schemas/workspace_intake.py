from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.constants.workspace_intake import WORKSPACE_INTAKE_PACKAGE_CODES


class WorkspaceIntakeCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    confirm_email: EmailStr
    phone_number: str = Field(..., min_length=1, max_length=30)
    selected_package_code: str = Field(..., min_length=1, max_length=32)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_names(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("Required")
        return s

    @field_validator("selected_package_code")
    @classmethod
    def package_must_be_locked(cls, v: str) -> str:
        code = (v or "").strip()
        if code not in WORKSPACE_INTAKE_PACKAGE_CODES:
            raise ValueError("Invalid selected_package_code")
        return code

    @field_validator("phone_number")
    @classmethod
    def phone_non_empty(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("Phone is required")
        return s

    @model_validator(mode="after")
    def emails_match(self):
        e = str(self.email).lower().strip()
        c = str(self.confirm_email).lower().strip()
        if e != c:
            raise ValueError("Email and confirm_email must match")
        return self


class WorkspaceIntakeCreateResponse(BaseModel):
    ok: bool = True
    message: str = "If this email can receive mail, you will get a link to continue shortly."


class WorkspaceIntakeConsumeRequest(BaseModel):
    intake_token: str = Field(..., min_length=10, max_length=512)


class WorkspaceIntakeConsumeResponse(BaseModel):
    ok: bool = True
    selected_package_code: str
    first_name: str
    last_name: str
    email: str
    phone_number: str


class WorkspaceIntakeSessionResponse(BaseModel):
    selected_package_code: str
    first_name: str
    last_name: str
    email: str
    phone_number: str
