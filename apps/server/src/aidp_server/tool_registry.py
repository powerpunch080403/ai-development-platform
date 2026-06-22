from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.db.models import ToolRegistryEntry

from aidp_server.action_policy import ACTION_CATALOG

def seed_tool_registry(session: Session) -> None:
    existing = session.execute(
        select(ToolRegistryEntry)
    ).scalars().all()
    
    existing_map = {entry.tool_name: entry for entry in existing if entry.tool_version == "1.0"}

    for action_def in ACTION_CATALOG:
        if not action_def.enabled_in_tool_registry:
            continue
            
        tool_name = action_def.action_type
        category = tool_name.split(".")[0]
        # Preserving original idempotency/side-effect logic based on read/write heuristic
        has_side_effect = not any(word in tool_name for word in ["get", "list", "check", "preview", "evaluate"])
        
        entry = existing_map.get(tool_name)
        if entry:
            if entry.default_risk_level != action_def.risk_level:
                entry.default_risk_level = action_def.risk_level
        else:
            session.add(
                ToolRegistryEntry(
                    tool_name=tool_name,
                    tool_version="1.0",
                    category=category,
                    description=f"Baseline record contract for {tool_name}",
                    has_side_effect=has_side_effect,
                    default_risk_level=action_def.risk_level,
                    required_grants=None,
                    scope_evaluator=None,
                    idempotency_required=has_side_effect,
                    approval_behavior="approval_required" if action_def.requires_approval else "policy",
                    audit_required=True,
                    enabled=True,
                )
            )
    session.commit()
