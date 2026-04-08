"""
Pydantic v2 models for the Mail Classification & Routing Environment.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Label enumerations
# ---------------------------------------------------------------------------

class SpamLabel(str, Enum):
    SPAM = "Spam"
    HAM = "Ham"


class PriorityLabel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DepartmentLabel(str, Enum):
    HR = "HR"
    TECH_SUPPORT = "Tech_Support"
    BILLING = "Billing"
    LEGAL = "Legal"
    SALES = "Sales"


class TaskTier(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# ---------------------------------------------------------------------------
# Action model
# ---------------------------------------------------------------------------

class MailAction(BaseModel):
    """Action produced by the agent for a single email observation."""

    label: str = Field(
        ...,
        description=(
            "Classification label. "
            "Easy  → 'Spam' | 'Ham'. "
            "Medium → 'High' | 'Medium' | 'Low'. "
            "Hard  → 'HR' | 'Tech_Support' | 'Billing' | 'Legal' | 'Sales'."
        ),
    )
    priority: Optional[str] = Field(
        default=None,
        description=(
            "Only required for the Hard tier. "
            "Set to 'High', 'Medium', or 'Low' to earn partial-reward credit."
        ),
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional agent self-assessed confidence in [0, 1].",
    )

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Observation model
# ---------------------------------------------------------------------------

class MailMetadata(BaseModel):
    """Structured metadata attached to each email."""

    sender: str = Field(..., description="Sender email address.")
    recipient: str = Field(..., description="Recipient email address.")
    timestamp: str = Field(..., description="ISO-8601 send timestamp.")
    has_attachment: bool = Field(default=False)
    attachment_names: list[str] = Field(default_factory=list)
    thread_id: Optional[str] = Field(default=None)
    reply_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)


class MailObservation(BaseModel):
    """A single email observation exposed to the agent."""

    email_id: str = Field(..., description="Unique email identifier.")
    subject: str = Field(..., description="Email subject line.")
    body: str = Field(..., description="Full email body text.")
    metadata: MailMetadata

    # Task context
    task_tier: TaskTier = Field(..., description="Which task tier this email belongs to.")
    task_description: str = Field(
        ...,
        description="Natural-language instruction telling the agent what to do.",
    )

    # Queue progress (informational)
    queue_position: int = Field(..., ge=0, description="0-based index in the email queue.")
    queue_total: int = Field(..., ge=1, description="Total number of emails in the queue.")

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Step result model
# ---------------------------------------------------------------------------

class StepResult(BaseModel):
    """Returned by MailEnv.step()."""

    observation: Optional[MailObservation] = Field(
        default=None,
        description="Next email to classify, or None when the queue is exhausted.",
    )
    reward: float = Field(..., description="Reward for the submitted action.")
    done: bool = Field(..., description="True when the episode is finished.")
    info: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic / grading information.",
    )