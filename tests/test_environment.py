"""
tests/test_environment.py
=========================
Unit tests for MailEnv. Run with: pytest
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from models import MailAction, MailObservation, TaskTier
from server.environment import MailEnv


@pytest.fixture
def env() -> MailEnv:
    return MailEnv()


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

def test_reset_returns_observation(env: MailEnv) -> None:
    obs = env.reset(seed=42)
    assert isinstance(obs, MailObservation)


def test_reset_easy_tier(env: MailEnv) -> None:
    obs = env.reset(seed=1, task_tier="easy")
    assert obs.task_tier == TaskTier.EASY


def test_reset_medium_tier(env: MailEnv) -> None:
    obs = env.reset(seed=1, task_tier="medium")
    assert obs.task_tier == TaskTier.MEDIUM


def test_reset_hard_tier(env: MailEnv) -> None:
    obs = env.reset(seed=1, task_tier="hard")
    assert obs.task_tier == TaskTier.HARD


def test_reset_invalid_tier_raises(env: MailEnv) -> None:
    with pytest.raises(ValueError):
        env.reset(task_tier="ultra")


def test_reset_all_tiers(env: MailEnv) -> None:
    obs = env.reset(seed=0)
    assert obs.queue_total > 0


# ---------------------------------------------------------------------------
# step() — easy tier
# ---------------------------------------------------------------------------

def test_easy_correct_spam(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="easy")
    # easy_001 is Spam
    result = env.step(MailAction(label="Spam"))
    assert result.reward == 1.0


def test_easy_wrong_label(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="easy")
    # easy_001 is Spam; answering Ham should give 0
    result = env.step(MailAction(label="Ham"))
    assert result.reward == 0.0


# ---------------------------------------------------------------------------
# step() — hard tier (partial rewards)
# ---------------------------------------------------------------------------

def test_hard_correct_dept_and_priority(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="hard")
    # hard_001 → Tech_Support, High
    result = env.step(MailAction(label="Tech_Support", priority="High"))
    assert result.reward == 1.5  # 1.0 + 0.5


def test_hard_correct_dept_wrong_priority(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="hard")
    result = env.step(MailAction(label="Tech_Support", priority="Low"))
    assert result.reward == 1.0  # dept only


def test_hard_wrong_dept_correct_priority(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="hard")
    result = env.step(MailAction(label="Sales", priority="High"))
    assert result.reward == 0.5  # priority only


def test_hard_all_wrong(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="hard")
    result = env.step(MailAction(label="HR", priority="Low"))
    assert result.reward == 0.0


# ---------------------------------------------------------------------------
# done state
# ---------------------------------------------------------------------------

def test_done_after_all_emails(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="easy")
    result = None
    while not (result and result.done):
        result = env.step(MailAction(label="Ham"))
    assert result.done
    assert result.observation is None


def test_step_after_done_raises(env: MailEnv) -> None:
    env.reset(seed=42, task_tier="easy")
    for _ in range(100):
        r = env.step(MailAction(label="Ham"))
        if r.done:
            break
    with pytest.raises(RuntimeError):
        env.step(MailAction(label="Ham"))


# ---------------------------------------------------------------------------
# state() / from_state()
# ---------------------------------------------------------------------------

def test_state_is_json_serialisable(env: MailEnv) -> None:
    import json
    env.reset(seed=7, task_tier="medium")
    env.step(MailAction(label="High"))
    snapshot = env.state()
    dumped = json.dumps(snapshot)
    assert isinstance(dumped, str)


def test_state_round_trip(env: MailEnv) -> None:
    import json
    env.reset(seed=99, task_tier="hard")
    env.step(MailAction(label="Billing", priority="High"))
    snapshot_before = env.state()

    env2 = MailEnv.from_state(snapshot_before)
    snapshot_after = env2.state()

    assert json.dumps(snapshot_before, sort_keys=True) == json.dumps(snapshot_after, sort_keys=True)


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------

def test_grader_report_at_end(env: MailEnv) -> None:
    env.reset(seed=0, task_tier="easy")
    result = None
    while not (result and result.done):
        result = env.step(MailAction(label="Spam"))
    report = result.info["grader_report"]
    assert "overall_score" in report
    assert 0.0 <= report["overall_score"] <= 1.0
    assert "tier_breakdown" in report