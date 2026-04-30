import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.agent_command import AgentCommand, COMMAND_TYPES
from app.models.agent_status import AgentStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def _command_to_dict(cmd: AgentCommand) -> dict:
    return {
        "id": cmd.id,
        "user_id": cmd.user_id,
        "type": cmd.type,
        "payload": cmd.payload,
        "status": cmd.status,
        "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
        "processed_at": cmd.processed_at.isoformat() if cmd.processed_at else None,
    }


def _status_to_dict(s: AgentStatus) -> dict:
    return {
        "user_id": s.user_id,
        "running": s.running,
        "paused": s.paused,
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "platform_health": s.platform_health,
        "ai_keys_configured": s.ai_keys_configured,
        "version": s.version,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


class CommandCreate(BaseModel):
    type: str
    payload: dict = {}


class CommandAck(BaseModel):
    result: str | None = None   # "done" | "failed"
    error: str | None = None


class AgentStatusPush(BaseModel):
    running: bool
    paused: bool
    last_seen: str | None = None
    platform_health: dict = {}
    ai_keys_configured: dict = {}
    version: str | None = None


@router.get("/api/agent/commands")
async def get_commands(
    status: str = Query(default="pending"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's commands matching the given status, sorted by created_at ASC."""
    result = await db.execute(
        select(AgentCommand)
        .where(and_(AgentCommand.user_id == user.id, AgentCommand.status == status))
        .order_by(AgentCommand.created_at.asc())
    )
    commands = result.scalars().all()
    return [_command_to_dict(c) for c in commands]


@router.post("/api/agent/commands")
async def create_command(
    data: CommandCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Web app inserts a command (e.g. pause_agent, resume_agent).
    Validates type is in COMMAND_TYPES.
    """
    if data.type not in COMMAND_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid command type '{data.type}'. Must be one of: {', '.join(COMMAND_TYPES)}",
        )
    cmd = AgentCommand(
        user_id=user.id,
        type=data.type,
        payload=data.payload,
        status="pending",
    )
    db.add(cmd)
    await db.flush()
    return _command_to_dict(cmd)


@router.post("/api/agent/commands/{command_id}/ack")
async def ack_command(
    command_id: int,
    data: CommandAck,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daemon acknowledges a command. Transitions pending/processing → done|failed."""
    result = await db.execute(
        select(AgentCommand).where(AgentCommand.id == command_id)
    )
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your command")
    if cmd.status in ("done", "failed"):
        raise HTTPException(status_code=400, detail=f"Command already {cmd.status}")

    final_status = "failed" if data.result == "failed" else "done"
    cmd.status = final_status
    cmd.processed_at = datetime.now(timezone.utc)
    await db.flush()
    return _command_to_dict(cmd)


@router.post("/api/agent/status")
async def push_agent_status(
    data: AgentStatusPush,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daemon pushes its current health. UPSERT on user_id (one row per user)."""
    result = await db.execute(
        select(AgentStatus).where(AgentStatus.user_id == user.id)
    )
    status_row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    # Use provided last_seen if given, else default to now
    last_seen_dt = now
    if data.last_seen:
        try:
            last_seen_dt = datetime.fromisoformat(data.last_seen)
        except ValueError:
            last_seen_dt = now

    if status_row is None:
        status_row = AgentStatus(
            user_id=user.id,
            running=data.running,
            paused=data.paused,
            last_seen=last_seen_dt,
            platform_health=data.platform_health,
            ai_keys_configured=data.ai_keys_configured,
            version=data.version,
        )
        db.add(status_row)
    else:
        status_row.running = data.running
        status_row.paused = data.paused
        status_row.last_seen = last_seen_dt
        status_row.platform_health = data.platform_health
        status_row.ai_keys_configured = data.ai_keys_configured
        status_row.version = data.version
        status_row.updated_at = now

    await db.flush()
    return _status_to_dict(status_row)


@router.get("/api/agent/status")
async def get_agent_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest agent status for the authenticated user, or 404."""
    result = await db.execute(
        select(AgentStatus).where(AgentStatus.user_id == user.id)
    )
    status_row = result.scalar_one_or_none()
    if not status_row:
        raise HTTPException(status_code=404, detail="No agent status yet")
    return _status_to_dict(status_row)
