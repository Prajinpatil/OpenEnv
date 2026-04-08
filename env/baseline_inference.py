"""
baseline_inference.py
=====================
Runs an LLM-powered agent through the mail_pro_env environment and prints
a detailed score breakdown.

Supports two backends (set via env var BACKEND):
  - openai   → uses the OpenAI Chat Completions API  (default)
  - hf       → uses a HuggingFace Inference Endpoint

Environment variables
---------------------
OPENAI_API_KEY   : Required for the 'openai' backend.
OPENAI_MODEL     : OpenAI model name (default: gpt-4o-mini).
HF_API_KEY       : Required for the 'hf' backend.
HF_ENDPOINT_URL  : HuggingFace endpoint URL for the 'hf' backend.
BACKEND          : 'openai' or 'hf' (default: 'openai').
TASK_TIER        : 'easy', 'medium', 'hard', or 'all' (default: 'all').
SEED             : Integer seed for reproducibility (default: 42).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

# Make sure the environment root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from models import MailAction, MailObservation, StepResult
from server.environment import MailEnv

# ---------------------------------------------------------------------------
# LLM back-end helpers
# ---------------------------------------------------------------------------

def _call_openai(prompt: str, model: str, api_key: str) -> str:
    """Call the OpenAI Chat Completions API and return the assistant reply."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise ImportError("openai package not installed. Run: uv add openai")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert email classification agent. "
                    "You always respond with valid JSON only — no markdown, no preamble."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"


def _call_hf(prompt: str, endpoint_url: str, api_key: str) -> str:
    """Call a HuggingFace Inference Endpoint and return the reply."""
    try:
        import requests  # type: ignore
    except ImportError:
        raise ImportError("requests package not installed. Run: uv add requests")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "inputs": f"<s>[INST] {prompt} [/INST]",
        "parameters": {"max_new_tokens": 256, "temperature": 0.01},
    }
    r = requests.post(endpoint_url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    raw = data[0]["generated_text"] if isinstance(data, list) else str(data)
    # Extract JSON from the response
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return raw[start:end] if start != -1 else "{}"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(obs: MailObservation) -> str:
    meta = obs.metadata
    return f"""
TASK: {obs.task_description}

EMAIL DETAILS
-------------
Email ID   : {obs.email_id}
Subject    : {obs.subject}
From       : {meta.sender}
To         : {meta.recipient}
Timestamp  : {meta.timestamp}
Attachments: {', '.join(meta.attachment_names) if meta.attachment_names else 'None'}
Tags       : {', '.join(meta.tags) if meta.tags else 'None'}

Body:
{obs.body}

Queue: email {obs.queue_position + 1} of {obs.queue_total}

INSTRUCTIONS
------------
Respond with a JSON object containing:
  "label"      : (string) your classification label
  "priority"   : (string or null) 'High', 'Medium', or 'Low' — required for 'hard' tier only
  "confidence" : (float) your confidence score between 0.0 and 1.0
  "reasoning"  : (string) brief one-sentence explanation

Example response format:
{{"label": "Billing", "priority": "High", "confidence": 0.92, "reasoning": "Invoice dispute requiring immediate financial attention."}}
""".strip()


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def parse_action(raw_json: str) -> MailAction:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"  [WARN] Could not parse LLM JSON: {exc}. Using empty label.")
        data = {}
    return MailAction(
        label=data.get("label", ""),
        priority=data.get("priority"),
        confidence=data.get("confidence"),
    )


def run_episode(
    env: MailEnv,
    backend: str,
    task_tier: Optional[str],
    seed: int,
    openai_model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Run one full episode and return the grader report."""
    obs: MailObservation = env.reset(seed=seed, task_tier=task_tier, shuffle=False)

    openai_key = os.getenv("OPENAI_API_KEY", "")
    hf_key = os.getenv("HF_API_KEY", "")
    hf_endpoint = os.getenv("HF_ENDPOINT_URL", "")

    step_num = 0
    final_info: dict[str, Any] = {}

    while True:
        prompt = build_prompt(obs)

        # Call LLM
        try:
            if backend == "openai":
                raw = _call_openai(prompt, openai_model, openai_key)
            elif backend == "hf":
                raw = _call_hf(prompt, hf_endpoint, hf_key)
            else:
                raise ValueError(f"Unknown backend: {backend!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERROR] LLM call failed: {exc}")
            raw = '{"label": "Ham"}'  # fallback

        action = parse_action(raw)
        result: StepResult = env.step(action)

        step_num += 1
        reward_str = f"{result.reward:.2f}"
        correct_indicator = "✓" if result.reward > 0 else "✗"

        print(
            f"  [{step_num:02d}] {obs.email_id:<15} "
            f"tier={result.info.get('tier','?'):<8} "
            f"label={action.label:<15} "
            f"reward={reward_str:<6} {correct_indicator}"
        )

        if result.done:
            final_info = result.info
            break
        assert result.observation is not None
        obs = result.observation

    return final_info


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    backend = os.getenv("BACKEND", "openai").lower()
    task_tier_input = os.getenv("TASK_TIER", "all").lower()
    seed = int(os.getenv("SEED", "42"))
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    task_tier: Optional[str] = None if task_tier_input == "all" else task_tier_input

    print("=" * 65)
    print("  mail_pro_env — Baseline LLM Agent")
    print("=" * 65)
    print(f"  Backend    : {backend}")
    print(f"  Task Tier  : {task_tier or 'all'}")
    print(f"  Seed       : {seed}")
    print(f"  Model      : {openai_model if backend == 'openai' else 'HF endpoint'}")
    print("=" * 65)

    env = MailEnv()
    print("\nRunning episode...\n")
    final_info = run_episode(
        env,
        backend=backend,
        task_tier=task_tier,
        seed=seed,
        openai_model=openai_model,
    )

    # ── Print grader report ───────────────────────────────────────────────
    report: dict[str, Any] = final_info.get("grader_report", {})

    print("\n" + "=" * 65)
    print("  GRADER REPORT")
    print("=" * 65)
    print(f"  Overall Score     : {report.get('overall_score', 0.0):.4f}  "
          f"({report.get('total_reward', 0):.2f} / {report.get('max_possible_reward', 0):.2f})")
    print(f"  Emails Processed  : {report.get('total_emails', 0)}")

    tier_breakdown = report.get("tier_breakdown", {})
    if tier_breakdown:
        print("\n  Per-Tier Breakdown:")
        for tier_name, stats in tier_breakdown.items():
            print(
                f"    {tier_name:<10} "
                f"score={stats['score']:.4f}  "
                f"reward={stats['total_reward']:.2f}/{stats['max_possible_reward']:.2f}  "
                f"emails={stats['emails_processed']}"
            )

    # Episode rewards
    ep_rewards = final_info.get("episode_rewards", [])
    if ep_rewards:
        avg = sum(ep_rewards) / len(ep_rewards)
        print(f"\n  Average reward/email : {avg:.4f}")

    print("=" * 65)
    print("  Episode complete.")
    print("=" * 65)


if __name__ == "__main__":
    main()