# models/schemas.py
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

class PolicyEvent:
    """
    Represents an insurance policy event in the system.
    """
    def __init__(
        self,
        event_type: str,
        customer_id: str,
        policy_id: str,
        policy_type: str,
        premium_amount: float,
        coverage_amount: float,
        start_date: str,
        end_date: str,
        risk_score: float,
        source_system: str = "batch_process",
        processing_priority: str = "standard",
        event_id: Optional[str] = None,
        event_timestamp: Optional[str] = None
    ):
        self.event_id = event_id or str(uuid.uuid4())
        self.event_timestamp = event_timestamp or datetime.utcnow().isoformat() + "Z"
        self.event_type = event_type
        self.customer_id = customer_id
        self.policy_details = {
            "policy_id": policy_id,
            "policy_type": policy_type,
            "premium_amount": premium_amount,
            "coverage_amount": coverage_amount,
            "start_date": start_date,
            "end_date": end_date,
            "risk_score": risk_score
        }
        self.metadata = {
            "source_system": source_system,
            "processing_priority": processing_priority
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary"""
        return {
            "event_id": self.event_id,
            "event_timestamp": self.event_timestamp,
            "event_type": self.event_type,
            "customer_id": self.customer_id,
            "policy_details": self.policy_details,
            "metadata": self.metadata
        }
    
    def to_json(self) -> str:
        """Convert the event to a JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PolicyEvent':
        """Create an instance from a dictionary"""
        return cls(
            event_type=data["event_type"],
            customer_id=data["customer_id"],
            policy_id=data["policy_details"]["policy_id"],
            policy_type=data["policy_details"]["policy_type"],
            premium_amount=data["policy_details"]["premium_amount"],
            coverage_amount=data["policy_details"]["coverage_amount"],
            start_date=data["policy_details"]["start_date"],
            end_date=data["policy_details"]["end_date"],
            risk_score=data["policy_details"]["risk_score"],
            source_system=data["metadata"]["source_system"],
            processing_priority=data["metadata"]["processing_priority"],
            event_id=data.get("event_id"),
            event_timestamp=data.get("event_timestamp")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PolicyEvent':
        """Create an instance from a JSON string"""
        return cls.from_dict(json.loads(json_str))
