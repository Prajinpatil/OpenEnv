"""
server/app.py
=============
Thin FastAPI wrapper that exposes the MailEnv over HTTP,
following the standard OpenEnv REST API contract.

Endpoints
---------
POST /reset           → MailObservation (JSON)
POST /step            → StepResult      (JSON)
GET  /state           → dict            (JSON)
GET  /health          → {"status": "ok"}
"""

from __future__ import annotations

import sys
import os

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models import MailAction, StepResult, MailObservation
from server.environment import MailEnv

app = FastAPI(
    title="mail_pro_env",
    description="OpenEnv Mail Classification & Routing Environment",
    version="1.0.0",
)

# Single shared environment instance (stateful per-process)
_env = MailEnv()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    seed: Optional[int] = None
    task_tier: Optional[str] = None  # 'easy' | 'medium' | 'hard' | None (all)
    shuffle: bool = False


class StepRequest(BaseModel):
    action: MailAction


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": MailEnv.ENV_NAME, "version": MailEnv.VERSION}


@app.post("/reset", response_model=MailObservation)
def reset(req: ResetRequest) -> MailObservation:
    try:
        obs = _env.reset(
            seed=req.seed,
            task_tier=req.task_tier,
            shuffle=req.shuffle,
        )
        return obs
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/step", response_model=StepResult)
def step(req: StepRequest) -> StepResult:
    try:
        result = _env.step(req.action)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/state")
def state() -> JSONResponse:
    return JSONResponse(content=_env.state())