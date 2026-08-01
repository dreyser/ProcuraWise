import string
from dataclasses import dataclass
from pathlib import Path

# service/procurawise/ai/prompt_renderer.py -> service/procurawise/ai/prompts
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class MissingPromptVariableError(Exception):
    """A prompt template referenced a variable that render_prompt() wasn't
    given - fails loudly rather than silently rendering "$missing" into a
    live prompt (ADR 0021 §11)."""


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str


def _render_one(template_text: str, variables: dict[str, str]) -> str:
    try:
        return string.Template(template_text).substitute(variables)
    except KeyError as exc:
        raise MissingPromptVariableError(f"missing prompt variable: {exc}") from exc


def render_prompt(name: str, version: str, variables: dict[str, str]) -> RenderedPrompt:
    """Prompts are versioned files checked into git, not a database table -
    git history already gives free versioning/diffing/review (ADR 0021 §11).
    `name`/`version` become `AIExecution.prompt_template`/`.prompt_version`."""
    template_dir = PROMPTS_DIR / name / version
    system_text = (template_dir / "system.txt").read_text(encoding="utf-8")
    user_text = (template_dir / "user.txt").read_text(encoding="utf-8")
    return RenderedPrompt(
        system=_render_one(system_text, variables),
        user=_render_one(user_text, variables),
    )
