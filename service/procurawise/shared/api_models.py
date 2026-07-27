from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for every FastAPI request/response schema. `extra='forbid'` makes
    any unexpected field - especially server-managed ones like tenant_id,
    owner_user_id, or status - a 422 instead of a silently ignored value.
    See CLAUDE.md's mass-assignment rule."""

    model_config = ConfigDict(extra="forbid")
