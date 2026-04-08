"""
server/environment.py
=====================
Core OpenEnv environment: MailEnv

Implements the standard OpenEnv SDK interface:
    reset()  → MailObservation
    step()   → StepResult
    state()  → dict  (fully JSON-serialisable; allows replay)
"""

from __future__ import annotations

import copy
import json
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from models import (
    DepartmentLabel,
    MailAction,
    MailMetadata,
    MailObservation,
    PriorityLabel,
    SpamLabel,
    StepResult,
    TaskTier,
)

# ---------------------------------------------------------------------------
# Synthetic "Golden" email dataset
# ---------------------------------------------------------------------------

_GOLDEN_EMAILS: list[dict[str, Any]] = [
    # ── EASY (Spam / Ham) ───────────────────────────────────────────────────
    {
        "email_id": "easy_001",
        "subject": "Congratulations! You've won a $1,000,000 lottery prize",
        "body": (
            "Dear Winner, Your email was randomly selected in our annual lottery draw. "
            "To claim your $1,000,000 prize, click the link below and provide your bank details. "
            "This offer expires in 24 hours! Act NOW: http://totally-legit-lottery.xyz/claim"
        ),
        "metadata": {
            "sender": "winner@totally-legit-lottery.xyz",
            "recipient": "user@company.com",
            "timestamp": "2024-11-01T08:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Spam"},
    },
    {
        "email_id": "easy_002",
        "subject": "Team lunch this Friday — are you in?",
        "body": (
            "Hi everyone,\n\nWe're organising a team lunch this Friday at 12:30 PM "
            "at the Italian place on Main Street. Please reply if you can make it so I "
            "can book a table for the right number of people.\n\nCheers,\nSarah"
        ),
        "metadata": {
            "sender": "sarah@company.com",
            "recipient": "team@company.com",
            "timestamp": "2024-11-01T09:15:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_lunch_001",
            "reply_count": 3,
            "tags": ["internal", "social"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Ham"},
    },
    {
        "email_id": "easy_003",
        "subject": "URGENT: Cheap Meds — No Prescription Needed!!!",
        "body": (
            "Get V1AGRA, C!ALlS and more at 90% discount. No doctor visit required. "
            "100% safe and discreet shipping worldwide. Order today and get FREE shipping. "
            "Unsubscribe: http://spam-unsubscribe.ru"
        ),
        "metadata": {
            "sender": "pharma-deals@spam-unsubscribe.ru",
            "recipient": "user@company.com",
            "timestamp": "2024-11-01T10:30:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external", "suspicious"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Spam"},
    },
    {
        "email_id": "easy_004",
        "subject": "Q3 Financial Report — Review Required",
        "body": (
            "Dear Finance Team,\n\nPlease find attached the Q3 financial report for your review. "
            "I need your sign-off by end of day Thursday before I submit it to the board. "
            "Let me know if you have any questions.\n\nBest,\nMike Chen, CFO"
        ),
        "metadata": {
            "sender": "mike.chen@company.com",
            "recipient": "finance-team@company.com",
            "timestamp": "2024-11-01T11:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Q3_Financial_Report_2024.pdf"],
            "thread_id": "thread_finance_q3",
            "reply_count": 1,
            "tags": ["internal", "finance", "urgent"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Ham"},
    },
    {
        "email_id": "easy_005",
        "subject": "Make $5,000 per week working from home!",
        "body": (
            "Are you tired of your 9-to-5 job? Discover our proven system that lets "
            "ordinary people earn $5,000 or more every week from the comfort of their home. "
            "No experience needed. Join 50,000+ success stories. Limited spots available! "
            "Click here: http://work-from-home-scam.net/signup"
        ),
        "metadata": {
            "sender": "opportunity@work-from-home-scam.net",
            "recipient": "user@company.com",
            "timestamp": "2024-11-02T07:45:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Spam"},
    },
    {
        "email_id": "easy_006",
        "subject": "Updated project timeline — please review",
        "body": (
            "Hi Team,\n\nI've updated the project timeline to reflect the new deadlines "
            "agreed in yesterday's meeting. The key change is the deployment date has moved "
            "from Nov 15 to Nov 22. Please review the attached Gantt chart and flag any conflicts.\n\n"
            "Thanks,\nPriya"
        ),
        "metadata": {
            "sender": "priya.sharma@company.com",
            "recipient": "project-team@company.com",
            "timestamp": "2024-11-02T09:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Updated_Timeline_Nov2024.xlsx"],
            "thread_id": "thread_project_timeline",
            "reply_count": 2,
            "tags": ["internal", "project"],
        },
        "task_tier": "easy",
        "ground_truth": {"label": "Ham"},
    },
    # ── MEDIUM (Priority Sorting) ────────────────────────────────────────────
    {
        "email_id": "medium_001",
        "subject": "CRITICAL: Production server down — immediate action required",
        "body": (
            "Team,\n\nOur primary production server (prod-web-01) went down at 14:32 UTC. "
            "We are currently losing approximately $12,000 per minute in revenue. "
            "All hands on deck. I need a status update every 10 minutes. "
            "Customer support has been notified. SLA breach imminent.\n\nCTO"
        ),
        "metadata": {
            "sender": "cto@company.com",
            "recipient": "devops@company.com",
            "timestamp": "2024-11-03T14:35:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_outage_001",
            "reply_count": 0,
            "tags": ["internal", "critical", "incident"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "High"},
    },
    {
        "email_id": "medium_002",
        "subject": "Monthly newsletter — November edition",
        "body": (
            "Hi everyone,\n\nWelcome to the November edition of our company newsletter! "
            "This month we celebrate 5 years of the company, share employee spotlights, "
            "announce upcoming events, and recap October's achievements.\n\n"
            "Happy reading!\n\nComms Team"
        ),
        "metadata": {
            "sender": "comms@company.com",
            "recipient": "all-staff@company.com",
            "timestamp": "2024-11-04T08:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Nov_Newsletter.pdf"],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "newsletter"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "Low"},
    },
    {
        "email_id": "medium_003",
        "subject": "Contract renewal — decision needed by Friday",
        "body": (
            "Hi,\n\nOur vendor contract with CloudHost Inc. expires on November 30th. "
            "I need a decision on renewal vs. migration by this Friday (Nov 8) to ensure "
            "continuity of service. I've prepared a comparison doc — please review and reply.\n\n"
            "Regards,\nOps Manager"
        ),
        "metadata": {
            "sender": "ops@company.com",
            "recipient": "management@company.com",
            "timestamp": "2024-11-04T10:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Vendor_Comparison_2024.pdf"],
            "thread_id": "thread_contract_001",
            "reply_count": 1,
            "tags": ["internal", "contract", "decision-required"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "High"},
    },
    {
        "email_id": "medium_004",
        "subject": "Reminder: Mandatory security training due by end of month",
        "body": (
            "Dear Employee,\n\nThis is a reminder that the annual mandatory cybersecurity "
            "awareness training must be completed by November 30th. The training takes "
            "approximately 45 minutes. Access it through the HR portal.\n\nThank you,\nIT Security"
        ),
        "metadata": {
            "sender": "it-security@company.com",
            "recipient": "all-staff@company.com",
            "timestamp": "2024-11-05T09:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "compliance", "training"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "Medium"},
    },
    {
        "email_id": "medium_005",
        "subject": "Office plants — anyone want to adopt one?",
        "body": (
            "Hi all,\n\nWe're doing a refresh of the office plants. If anyone would like "
            "to adopt one of the current plants (we have 3 small succulents and a fern), "
            "please let me know by Wednesday. First come, first served!\n\nFacilities Team"
        ),
        "metadata": {
            "sender": "facilities@company.com",
            "recipient": "all-staff@company.com",
            "timestamp": "2024-11-05T11:30:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "social"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "Low"},
    },
    {
        "email_id": "medium_006",
        "subject": "Board meeting prep — slides needed by Thursday 9 AM",
        "body": (
            "Hi,\n\nThe quarterly board meeting is Friday at 10 AM. I need all department "
            "heads to send me their slides no later than Thursday 9 AM so I can compile the "
            "master deck. Missing slides will result in your section being cut.\n\nCEO Assistant"
        ),
        "metadata": {
            "sender": "ceo-assistant@company.com",
            "recipient": "dept-heads@company.com",
            "timestamp": "2024-11-05T15:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_board_prep",
            "reply_count": 4,
            "tags": ["internal", "urgent", "executive"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "High"},
    },
    {
        "email_id": "medium_007",
        "subject": "New coffee machine installed in Break Room B",
        "body": (
            "Hi Team,\n\nGreat news — a new Nespresso machine has been installed in Break Room B. "
            "Pods are provided by the company. Please remember to clean after use. "
            "Enjoy!\n\nFacilities"
        ),
        "metadata": {
            "sender": "facilities@company.com",
            "recipient": "floor-3@company.com",
            "timestamp": "2024-11-06T08:30:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "social"],
        },
        "task_tier": "medium",
        "ground_truth": {"label": "Low"},
    },
    # ── HARD (Department Routing) ────────────────────────────────────────────
    {
        "email_id": "hard_001",
        "subject": "Suspicious login attempt on my account — please help",
        "body": (
            "Hi,\n\nI received an alert saying someone tried to log into my company account "
            "from an IP in another country. I didn't make that login attempt. "
            "My account seems to still be accessible but I'm worried it may be compromised. "
            "Can you help me secure my account and investigate the incident?\n\nThanks,\nAlex"
        ),
        "metadata": {
            "sender": "alex.jones@company.com",
            "recipient": "helpdesk@company.com",
            "timestamp": "2024-11-07T09:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_security_001",
            "reply_count": 0,
            "tags": ["internal", "security", "urgent"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Tech_Support", "priority": "High"},
    },
    {
        "email_id": "hard_002",
        "subject": "Invoice dispute — incorrect charges on account #8821",
        "body": (
            "Dear Team,\n\nI'm reaching out regarding invoice #INV-2024-8821 dated October 15th. "
            "The invoice shows a charge of $4,500 for 'Enterprise Tier Services', but our "
            "contract specifies the Standard Tier at $2,200/month. This has been incorrectly "
            "billed for the past 3 months. Please issue corrected invoices and a refund of $6,900.\n\n"
            "Regards,\nJennifer Walsh, Acme Corp"
        ),
        "metadata": {
            "sender": "jennifer.walsh@acme-corp.com",
            "recipient": "support@company.com",
            "timestamp": "2024-11-07T10:30:00Z",
            "has_attachment": True,
            "attachment_names": ["INV-2024-8821.pdf", "Contract_Acme_2024.pdf"],
            "thread_id": "thread_dispute_8821",
            "reply_count": 0,
            "tags": ["external", "billing", "dispute"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Billing", "priority": "High"},
    },
    {
        "email_id": "hard_003",
        "subject": "Interest in enterprise licensing for 500+ users",
        "body": (
            "Hi,\n\nI'm the Head of Digital Transformation at GlobalBank and we're currently "
            "evaluating your product for deployment across our 500-person operations team. "
            "We're interested in an enterprise license and would like to discuss pricing, "
            "SLAs, and custom integration support. Could we schedule a call this week?\n\n"
            "Best,\nDavid Kim, GlobalBank"
        ),
        "metadata": {
            "sender": "david.kim@globalbank.com",
            "recipient": "info@company.com",
            "timestamp": "2024-11-07T11:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external", "lead", "enterprise"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Sales", "priority": "High"},
    },
    {
        "email_id": "hard_004",
        "subject": "Formal grievance notice — workplace harassment",
        "body": (
            "To Whom It May Concern,\n\nI am writing to formally raise a grievance against "
            "my line manager, who has subjected me to repeated verbal harassment over the past "
            "six weeks. I have kept a log of incidents with dates and witnesses. "
            "I request this matter be investigated confidentially and in accordance with the "
            "company's Code of Conduct.\n\nName withheld for safety"
        ),
        "metadata": {
            "sender": "anonymous-report@company.com",
            "recipient": "hr@company.com",
            "timestamp": "2024-11-07T13:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Incident_Log.pdf"],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "grievance", "confidential"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "HR", "priority": "High"},
    },
    {
        "email_id": "hard_005",
        "subject": "Cease and desist — unauthorised use of trademarked logo",
        "body": (
            "Dear Sir/Madam,\n\nWe represent TechBrand GmbH and write to notify you that "
            "your recent marketing campaign features imagery that infringes upon our registered "
            "trademark (EU Reg. No. 012345678). You are required to cease all use of this "
            "imagery within 14 days or we will initiate legal proceedings. "
            "Please confirm receipt and your intended course of action.\n\n"
            "Schmidt & Partners LLP"
        ),
        "metadata": {
            "sender": "legal@schmidt-partners.com",
            "recipient": "contact@company.com",
            "timestamp": "2024-11-07T14:00:00Z",
            "has_attachment": True,
            "attachment_names": ["Cease_and_Desist_Notice.pdf"],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external", "legal", "urgent"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Legal", "priority": "High"},
    },
    {
        "email_id": "hard_006",
        "subject": "Printer on 3rd floor not connecting to the network",
        "body": (
            "Hi Helpdesk,\n\nThe HP LaserJet printer in the 3rd floor meeting room (Room 302) "
            "has stopped showing up on the network. Staff are unable to print. The printer "
            "shows as online on its own display but is not visible in Windows print settings. "
            "This has been the case since this morning. Can someone look at it today?\n\nFacilities"
        ),
        "metadata": {
            "sender": "facilities@company.com",
            "recipient": "helpdesk@company.com",
            "timestamp": "2024-11-08T09:30:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_printer_3f",
            "reply_count": 0,
            "tags": ["internal", "it-issue"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Tech_Support", "priority": "Medium"},
    },
    {
        "email_id": "hard_007",
        "subject": "New hire start date — onboarding checklist request",
        "body": (
            "Hi HR Team,\n\nWe have a new team member, Ravi Patel, starting on December 2nd "
            "as a Senior Data Engineer. Could you please send over the onboarding checklist "
            "and ensure his laptop and system access are arranged in advance? "
            "Let me know if you need any details from my side.\n\nEngineering Manager"
        ),
        "metadata": {
            "sender": "eng-manager@company.com",
            "recipient": "hr@company.com",
            "timestamp": "2024-11-08T10:00:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["internal", "onboarding"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "HR", "priority": "Medium"},
    },
    {
        "email_id": "hard_008",
        "subject": "Follow-up: Demo call feedback and next steps",
        "body": (
            "Hi,\n\nThank you for the demo call last Thursday. Our team was impressed with the "
            "product's analytics dashboard. We'd like to move forward with a pilot for our "
            "marketing division (20 users). Could you send over a pilot proposal with pricing "
            "and setup timeline?\n\nBest,\nCarla Mendez, RetailCo"
        ),
        "metadata": {
            "sender": "c.mendez@retailco.com",
            "recipient": "sales@company.com",
            "timestamp": "2024-11-08T11:30:00Z",
            "has_attachment": False,
            "attachment_names": [],
            "thread_id": "thread_demo_retailco",
            "reply_count": 2,
            "tags": ["external", "prospect", "pilot"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Sales", "priority": "High"},
    },
    {
        "email_id": "hard_009",
        "subject": "GDPR data subject access request",
        "body": (
            "Dear Data Controller,\n\nPursuant to Article 15 of the UK GDPR, I am requesting "
            "access to all personal data you hold about me. Please provide this data in a "
            "machine-readable format within the statutory 30-day period. "
            "My full name and date of birth are attached for identity verification purposes.\n\n"
            "Emma Thompson"
        ),
        "metadata": {
            "sender": "emma.thompson@private.com",
            "recipient": "privacy@company.com",
            "timestamp": "2024-11-08T14:00:00Z",
            "has_attachment": True,
            "attachment_names": ["ID_Verification.pdf"],
            "thread_id": None,
            "reply_count": 0,
            "tags": ["external", "gdpr", "legal", "compliance"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Legal", "priority": "High"},
    },
    {
        "email_id": "hard_010",
        "subject": "Overdue invoice — INV-2024-7755 — payment reminder",
        "body": (
            "Dear Accounts Team,\n\nThis is a reminder that invoice INV-2024-7755 for $1,250 "
            "was due on October 31st and remains unpaid. We kindly request settlement within "
            "the next 5 business days to avoid a late payment fee. "
            "Payment details are in the original invoice.\n\nAccounts Receivable, VendorCo"
        ),
        "metadata": {
            "sender": "ar@vendorco.com",
            "recipient": "accounts@company.com",
            "timestamp": "2024-11-09T09:00:00Z",
            "has_attachment": True,
            "attachment_names": ["INV-2024-7755.pdf"],
            "thread_id": "thread_inv_7755",
            "reply_count": 0,
            "tags": ["external", "billing", "overdue"],
        },
        "task_tier": "hard",
        "ground_truth": {"label": "Billing", "priority": "Medium"},
    },
]

# Task descriptions surfaced to the agent
_TASK_DESCRIPTIONS: dict[str, str] = {
    "easy": (
        "Classify this email as exactly 'Spam' or 'Ham'. "
        "Spam = unsolicited, deceptive, or promotional junk mail. "
        "Ham = legitimate, expected communication."
    ),
    "medium": (
        "This email has already been confirmed as legitimate (Ham). "
        "Classify its priority as 'High', 'Medium', or 'Low'. "
        "High = immediate action required or significant business impact. "
        "Medium = action needed within 1-5 business days. "
        "Low = informational or social, no action required."
    ),
    "hard": (
        "Route this email to the correct department: "
        "'HR' (people/employment matters), "
        "'Tech_Support' (IT/technical issues), "
        "'Billing' (invoices/payments/charges), "
        "'Legal' (contracts/compliance/legal threats), or "
        "'Sales' (prospects/leads/commercial enquiries). "
        "Also set the 'priority' field to 'High', 'Medium', or 'Low'."
    ),
}


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------

@dataclass
class Grader:
    """Accumulates per-step rewards and produces a final score breakdown."""

    total_emails: int = 0
    total_reward: float = 0.0
    tier_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def record(self, tier: str, reward: float) -> None:
        if tier not in self.tier_stats:
            self.tier_stats[tier] = {"count": 0, "reward": 0.0}
        self.tier_stats[tier]["count"] += 1
        self.tier_stats[tier]["reward"] += reward
        self.total_emails += 1
        self.total_reward += reward

    def final_report(self) -> dict[str, Any]:
        max_possible = self._max_possible()
        overall = round(self.total_reward / max_possible, 4) if max_possible > 0 else 0.0
        tier_breakdown: dict[str, Any] = {}
        for tier, stats in self.tier_stats.items():
            count = stats["count"]
            reward = stats["reward"]
            mp = self._max_reward_for_tier(tier) * count
            tier_breakdown[tier] = {
                "emails_processed": count,
                "total_reward": round(reward, 4),
                "max_possible_reward": round(mp, 4),
                "score": round(reward / mp, 4) if mp > 0 else 0.0,
            }
        return {
            "overall_score": overall,
            "total_reward": round(self.total_reward, 4),
            "max_possible_reward": round(max_possible, 4),
            "total_emails": self.total_emails,
            "tier_breakdown": tier_breakdown,
        }

    def _max_reward_for_tier(self, tier: str) -> float:
        return {"easy": 1.0, "medium": 1.0, "hard": 1.5}.get(tier, 1.0)

    def _max_possible(self) -> float:
        return sum(
            self._max_reward_for_tier(tier) * stats["count"]
            for tier, stats in self.tier_stats.items()
        )


# ---------------------------------------------------------------------------
# MailEnv
# ---------------------------------------------------------------------------

class MailEnv:
    """
    OpenEnv-compatible environment for mail classification & routing.

    Public API
    ----------
    reset(seed, task_tier, shuffle) → MailObservation
    step(action)                    → StepResult
    state()                         → dict  (JSON-serialisable; full replay state)
    """

    ENV_NAME = "mail_pro_env"
    VERSION = "1.0.0"

    # Reward constants
    _REWARD_EASY_CORRECT: float = 1.0
    _REWARD_EASY_WRONG: float = 0.0
    _REWARD_MEDIUM_CORRECT: float = 1.0
    _REWARD_MEDIUM_WRONG: float = 0.0
    _REWARD_HARD_CORRECT_DEPT: float = 1.0
    _REWARD_HARD_CORRECT_PRIORITY: float = 0.5
    _REWARD_HARD_WRONG: float = 0.0

    def __init__(self) -> None:
        self._emails: list[dict[str, Any]] = []
        self._current_index: int = 0
        self._done: bool = True
        self._seed: Optional[int] = None
        self._task_tier: Optional[str] = None
        self._grader: Grader = Grader()
        self._episode_rewards: list[float] = []

    # ------------------------------------------------------------------ #
    # reset                                                                #
    # ------------------------------------------------------------------ #

    def reset(
        self,
        seed: Optional[int] = None,
        task_tier: Optional[str] = None,
        shuffle: bool = False,
    ) -> MailObservation:
        """
        Start a new episode.

        Parameters
        ----------
        seed        : RNG seed for reproducibility.
        task_tier   : Filter to 'easy', 'medium', or 'hard'. None = all tiers.
        shuffle     : Shuffle the email order when True.
        """
        self._seed = seed if seed is not None else random.randint(0, 2**31)
        self._task_tier = task_tier
        self._grader = Grader()
        self._episode_rewards = []

        rng = random.Random(self._seed)

        emails = (
            [e for e in _GOLDEN_EMAILS if e["task_tier"] == task_tier]
            if task_tier
            else list(_GOLDEN_EMAILS)
        )

        if not emails:
            raise ValueError(f"No emails found for task_tier={task_tier!r}")

        if shuffle:
            rng.shuffle(emails)

        self._emails = emails
        self._current_index = 0
        self._done = False

        return self._make_observation()

    # ------------------------------------------------------------------ #
    # step                                                                 #
    # ------------------------------------------------------------------ #

    def step(self, action: MailAction) -> StepResult:
        """Submit a classification action and advance to the next email."""
        if self._done:
            raise RuntimeError("Episode is done. Call reset() to start a new episode.")

        current_email = self._emails[self._current_index]
        tier = current_email["task_tier"]
        ground_truth = current_email["ground_truth"]

        reward, info = self._calculate_reward(action, ground_truth, tier)
        self._grader.record(tier, reward)
        self._episode_rewards.append(reward)

        self._current_index += 1
        done = self._current_index >= len(self._emails)
        self._done = done

        next_obs: Optional[MailObservation] = None
        if not done:
            next_obs = self._make_observation()

        if done:
            info["grader_report"] = self._grader.final_report()
            info["episode_rewards"] = self._episode_rewards

        return StepResult(
            observation=next_obs,
            reward=reward,
            done=done,
            info=info,
        )

    # ------------------------------------------------------------------ #
    # state                                                                #
    # ------------------------------------------------------------------ #

    def state(self) -> dict[str, Any]:
        """
        Return a fully JSON-serialisable snapshot of the current environment state.
        This snapshot can be used to perfectly reconstruct / replay the episode.
        """
        return {
            "env_name": self.ENV_NAME,
            "version": self.VERSION,
            "seed": self._seed,
            "task_tier": self._task_tier,
            "current_index": self._current_index,
            "total_emails": len(self._emails),
            "done": self._done,
            "emails": copy.deepcopy(self._emails),
            "episode_rewards": list(self._episode_rewards),
            "grader_state": copy.deepcopy(self._grader.tier_stats),
        }

    @classmethod
    def from_state(cls, snapshot: dict[str, Any]) -> "MailEnv":
        """Reconstruct a MailEnv instance from a state snapshot."""
        env = cls()
        env._seed = snapshot["seed"]
        env._task_tier = snapshot["task_tier"]
        env._current_index = snapshot["current_index"]
        env._done = snapshot["done"]
        env._emails = snapshot["emails"]
        env._episode_rewards = snapshot["episode_rewards"]
        env._grader.tier_stats = snapshot["grader_state"]
        env._grader.total_emails = sum(
            v["count"] for v in snapshot["grader_state"].values()
        )
        env._grader.total_reward = sum(
            v["reward"] for v in snapshot["grader_state"].values()
        )
        return env

    # ------------------------------------------------------------------ #
    # Reward calculation                                                   #
    # ------------------------------------------------------------------ #

    def _calculate_reward(
        self,
        action: MailAction,
        ground_truth: dict[str, Any],
        tier: str,
    ) -> tuple[float, dict[str, Any]]:
        info: dict[str, Any] = {
            "tier": tier,
            "ground_truth": ground_truth,
            "agent_label": action.label,
            "agent_priority": action.priority,
        }

        if tier == "easy":
            reward, detail = self._reward_easy(action, ground_truth)
        elif tier == "medium":
            reward, detail = self._reward_medium(action, ground_truth)
        elif tier == "hard":
            reward, detail = self._reward_hard(action, ground_truth)
        else:
            reward, detail = 0.0, {"error": f"Unknown tier: {tier}"}

        info.update(detail)
        return reward, info

    def _reward_easy(
        self, action: MailAction, gt: dict[str, Any]
    ) -> tuple[float, dict[str, Any]]:
        correct = action.label == gt["label"]
        reward = self._REWARD_EASY_CORRECT if correct else self._REWARD_EASY_WRONG
        return reward, {
            "correct": correct,
            "reward_breakdown": {"label": reward},
        }

    def _reward_medium(
        self, action: MailAction, gt: dict[str, Any]
    ) -> tuple[float, dict[str, Any]]:
        correct = action.label == gt["label"]
        reward = self._REWARD_MEDIUM_CORRECT if correct else self._REWARD_MEDIUM_WRONG
        return reward, {
            "correct": correct,
            "reward_breakdown": {"priority": reward},
        }

    def _reward_hard(
        self, action: MailAction, gt: dict[str, Any]
    ) -> tuple[float, dict[str, Any]]:
        """
        Partial rewards:
          +1.0  correct department
          +0.5  correct priority  (in addition to department reward)
          +0.5  correct priority only, department wrong  (partial credit)
           0.0  both wrong
        """
        dept_correct = action.label == gt["label"]
        priority_correct = (
            action.priority is not None
            and action.priority == gt.get("priority")
        )

        reward = 0.0
        if dept_correct:
            reward += self._REWARD_HARD_CORRECT_DEPT
        if priority_correct:
            reward += self._REWARD_HARD_CORRECT_PRIORITY

        breakdown = {
            "dept_reward": self._REWARD_HARD_CORRECT_DEPT if dept_correct else 0.0,
            "priority_reward": self._REWARD_HARD_CORRECT_PRIORITY if priority_correct else 0.0,
        }
        return reward, {
            "dept_correct": dept_correct,
            "priority_correct": priority_correct,
            "reward_breakdown": breakdown,
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _make_observation(self) -> MailObservation:
        raw = self._emails[self._current_index]
        return MailObservation(
            email_id=raw["email_id"],
            subject=raw["subject"],
            body=raw["body"],
            metadata=MailMetadata(**raw["metadata"]),
            task_tier=TaskTier(raw["task_tier"]),
            task_description=_TASK_DESCRIPTIONS[raw["task_tier"]],
            queue_position=self._current_index,
            queue_total=len(self._emails),
        )

    def __repr__(self) -> str:
        return (
            f"MailEnv(tier={self._task_tier!r}, "
            f"index={self._current_index}/{len(self._emails)}, "
            f"done={self._done})"
        )