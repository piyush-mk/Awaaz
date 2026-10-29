"""Voice agent (Phase 1, Agent A: Counter).

POST /api/agent/utterance   multipart: audio | text, context (counter|stock|khata|ask), session_id.
                            Header X-Demo-Phrase picks a fixture transcript when STT is unavailable.
                            Flow: sarvam.stt -> (rules parser now, llm.complete_or_rules reconciles)
                            -> cart edits applied, money/stock changes become PendingAction rows.
POST /api/actions/{id}/confirm | /cancel   resolve a PendingAction (Agent A owns; others register
                            their commit handlers for their own `kind`).
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()
actions_router = APIRouter()


@router.post("/utterance")
async def utterance():
    not_implemented("POST /api/agent/utterance", "Agent A")


@actions_router.get("")
def list_actions():
    not_implemented("GET /api/actions", "Agent A")


@actions_router.get("/{action_id}")
def get_action(action_id: int):
    not_implemented("GET /api/actions/{id}", "Agent A")


@actions_router.post("/{action_id}/confirm")
def confirm_action(action_id: int):
    not_implemented("POST /api/actions/{id}/confirm", "Agent A")


@actions_router.post("/{action_id}/cancel")
def cancel_action(action_id: int):
    not_implemented("POST /api/actions/{id}/cancel", "Agent A")
