from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PayDocumentSummary(BaseModel):
    id: int
    pay_run_id: int
    payee_id: int
    document_type: str
    version: int
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)
