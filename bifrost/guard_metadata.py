"""
Guard metadata extraction morphisms

Functional composable functions to extract guard metadata from policies and registry
"""

from typing import Any

from heimdall.registry import get_guard_metadata, has_guard


def extract_guards_by_phase(policy_metadata: dict[str, Any], phase: str) -> list[str]:
    """
    Extract guard IDs for a specific phase from policy metadata

    Args:
        policy_metadata: Policy metadata from compilation
        phase: Phase name (input, output, mcp_request, etc.)

    Returns:
        List of guard IDs for the phase
    """
    guards_list = policy_metadata.get("guards", [])
    compose_section = policy_metadata.get("compose", {})
    compose_expr = compose_section.get(phase, compose_section.get("root", ""))

    # Extract guard IDs from compose expression
    # Convert dots to underscores as done in compiler
    guard_ids = []
    for guard_def in guards_list:
        guard_id = guard_def.get("id", "")
        guard_phase = guard_def.get("phase", "input")

        # Check if this guard's ID appears in the compose expression for this phase
        python_id = guard_id.replace(".", "_")
        if python_id in compose_expr or guard_phase == phase:
            guard_ids.append(guard_id)

    return guard_ids


def normalize_tier(tier: str) -> str:
    """Convert T0/T1/T2 to fast/medium/slow"""
    tier_map = {
        "T0": "fast",
        "T1": "medium",
        "T2": "slow"
    }
    return tier_map.get(tier, tier)


def get_guard_display_metadata(guard_id: str) -> dict[str, Any]:
    """
    Get display metadata for a guard from registry

    Args:
        guard_id: Guard ID

    Returns:
        Dict with id, name, tier, status, description
    """
    if not has_guard(guard_id):
        return {
            "id": guard_id,
            "name": guard_id.replace(".", " ").title(),
            "tier": "medium",
            "status": "unknown",
            "description": "Guard not found in registry"
        }

    metadata = get_guard_metadata(guard_id)

    return {
        "id": guard_id,
        "name": guard_id.replace(".", " ").title(),
        "tier": normalize_tier(metadata.tier or "T1"),
        "status": "passed",  # Default status, can be updated
        "description": metadata.description or f"Validates {guard_id}"
    }


def build_guards_metadata(policy_metadata: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    """
    Build guard metadata list for a phase

    Composition: extract_guards_by_phase -> map(get_guard_display_metadata)

    Args:
        policy_metadata: Policy metadata from compilation
        phase: Phase name

    Returns:
        List of guard display metadata
    """
    guard_ids = extract_guards_by_phase(policy_metadata, phase)
    return [get_guard_display_metadata(gid) for gid in guard_ids]


def mark_guard_as_blocked(guards: list[dict[str, Any]], rule_id: str, message: str) -> list[dict[str, Any]]:
    """
    Mark a specific guard as blocked (pure function)

    Args:
        guards: List of guard metadata
        rule_id: Rule ID that was violated
        message: Violation message

    Returns:
        New list with updated guard status
    """
    return [
        {
            **guard,
            "status": "blocked" if guard["id"] == rule_id else guard["status"],
            "violation_message": message if guard["id"] == rule_id else guard.get("violation_message")
        }
        for guard in guards
    ]


def get_fallback_guards(phase: str) -> list[dict[str, Any]]:
    """
    Get fallback guard metadata when policy metadata is not available

    Args:
        phase: Phase name

    Returns:
        Default guard metadata list
    """
    return [
        {
            "id": f"{phase}.validation",
            "name": f"{phase.title()} Validation",
            "tier": "medium",
            "status": "passed",
            "description": f"Validates {phase} against policy"
        }
    ]

