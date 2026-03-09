from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ProposeRequest(BaseModel):
    input_text: str
    session_id: Optional[str] = None

class ApproveRequest(BaseModel):
    session_id: str
    proposal_id: str
    edited_kb_json: Optional[List[Dict[str, Any]]] = None
