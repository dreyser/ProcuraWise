from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from procurawise.evaluations.models import ECONOMIC_MAX_POINTS
from procurawise.scoring.models import CriterionScore

# Fase 20 (ADR 0009): the fixed 70/15/15 split within the 40%-point economic
# dimension. Never configurable - only the sub-weights *within* commercial/
# risk are (plan §9 Pregunta Bloqueante #1, Opción 1).
_TCO_WEIGHT = 0.70
_COMMERCIAL_WEIGHT = 0.15
_RISK_WEIGHT = 0.15


@dataclass(frozen=True)
class TcoNormalizedResult:
    status: Literal["available", "no_comparable"]
    pct: float | None


@dataclass(frozen=True)
class EconomicSubtotalResult:
    status: Literal["available", "not_available"]
    earned_points: float | None


def calculate_tco_normalized_pct(
    proposal_tco_totals: dict[str, Decimal | None],
) -> dict[str, TcoNormalizedResult]:
    """Fase 20 (spec §7.5): "Menor TCO válido recibe 100; otros: menor TCO /
    TCO proveedor × 100." A proposal's own `grand_total` is None (no
    ProposalSnapshot.tco_result, e.g. zero CostItems captured) or <= 0
    (plan §9 R5 - never a real "free" bid in this context, and dividing by
    it would be undefined) is excluded from ever being the "menor válido"
    and from receiving a comparative score at all - `status="no_comparable"`
    for that proposal, without blocking the calculation for any other
    proposal in the same evaluation.

    Pure function: takes the already-frozen `grand_total` per proposal_id,
    never queries anything itself (same "caller resolves inputs" contract as
    tco.service.TcoService.calculate - see plan §12.2)."""
    valid = {
        pid: total for pid, total in proposal_tco_totals.items() if total is not None and total > 0
    }
    if not valid:
        return {
            pid: TcoNormalizedResult(status="no_comparable", pct=None)
            for pid in proposal_tco_totals
        }

    lowest = min(valid.values())
    results: dict[str, TcoNormalizedResult] = {}
    for proposal_id, total in proposal_tco_totals.items():
        if total is None or total <= 0:
            results[proposal_id] = TcoNormalizedResult(status="no_comparable", pct=None)
        else:
            pct = round(float(lowest / total) * 100, 2)
            results[proposal_id] = TcoNormalizedResult(status="available", pct=pct)
    return results


def calculate_rubric_pct(scores: list[CriterionScore], weights: dict[str, float]) -> float | None:
    """(score/5) × peso, sumado y renormalizado sobre el peso de los
    criterios aplicables únicamente (excluye "N/A" del denominador - mismo
    principio que spec §7.2 aplica a Requirements no aplicables, extendido
    por analogía a los sub-criterios económicos). Devuelve None si ningún
    criterio tiene un score numérico todavía (rúbrica sin empezar)."""
    applicable: list[tuple[int, float]] = [
        (s.score, weights[s.criterion_key]) for s in scores if s.score is not None
    ]
    if not applicable:
        return None
    total_weight = sum(weight for _, weight in applicable)
    if total_weight <= 0:
        return None
    weighted_sum = sum((score / 5) * weight for score, weight in applicable)
    return round(weighted_sum / total_weight * 100, 2)


def calculate_economic_points(
    tco_pct: float | None, commercial_pct: float | None, risk_pct: float | None
) -> EconomicSubtotalResult:
    """0-40 puntos (ECONOMIC_MAX_POINTS). `status="available"` únicamente
    cuando los 3 componentes (TCO normalizado, comercial, riesgo) están
    disponibles - mismo principio de completitud que el resto del modelo de
    scoring (plan §15, matriz de completitud)."""
    if tco_pct is None or commercial_pct is None or risk_pct is None:
        return EconomicSubtotalResult(status="not_available", earned_points=None)
    points = ECONOMIC_MAX_POINTS * (
        _TCO_WEIGHT * (tco_pct / 100)
        + _COMMERCIAL_WEIGHT * (commercial_pct / 100)
        + _RISK_WEIGHT * (risk_pct / 100)
    )
    return EconomicSubtotalResult(status="available", earned_points=round(points, 2))
