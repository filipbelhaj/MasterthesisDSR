from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel

SessionMode = Literal["create_new", "extend_existing"]

class ProposeRequest(BaseModel):
    input_text: str
    session_id: Optional[str] = None
    mode: Optional[SessionMode] = None

class ApproveRequest(BaseModel):
    session_id: str
    proposal_id: str
    edited_kb_json: Optional[List[Dict[str, Any]]] = None
