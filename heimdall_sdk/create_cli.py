"""
CLI for creating guardrails (guards and policies)

Usage:
    heimdall-create guard my_guard --type pii --tier T0
    heimdall-create policy my_policy --guards pii.email,toxicity.hate
"""

import argparse
import sys
from pathlib import Path

GUARD_TEMPLATE = '''"""
{description}
"""

from heimdall import guard, Guard, Ctx, Either, Left_, Right_, Violation
from typing import Dict, Any, List


@guard("{guard_id}", tier="{tier}", performance_budget_ms={budget_ms})
def {function_name}({params}) -> Guard:
    """
    {description}

    Args:
{param_docs}

    Returns:
        Guard function that checks context
    """
    async def check(ctx: Ctx) -> Either:
        # TODO: Implement your guard logic here
        violations: List[Violation] = []

        # Example: Check something in context
        # if condition_fails:
        #     violations.append(
        #         Violation(
        #             rule_id="{guard_id}",
        #             severity="high",
        #             message="Violation detected",
        #             tier="{tier}"
        #         )
    #     )

        if violations:
            return Left_(violations)

        return Right_(ctx)

    return check
'''

POLICY_TEMPLATE = '''# {policy_name}
# {description}

policy: {policy_id}
description: {description}

guards:
{guard_definitions}

compose:
  root: seq([{guard_sequence}])

thresholds:
  t0:
    gate_t1: 0.3
    gate_t2: 0.6
  t1:
    gate_t2: 0.4
'''

TIER_DEFAULTS = {
    "T0": {"budget_ms": 5.0, "description": "Ultra-fast (regex, simple checks)"},
    "T1": {"budget_ms": 20.0, "description": "Fast semantic (heuristics)"},
    "T2": {"budget_ms": 100.0, "description": "Heavy ML (ONNX models)"}
}


def create_guard(
    name: str,
    guard_type: str,
    tier: str,
    output_dir: Path,
    description: str | None = None
) -> None:
    """Create a new guard file"""

    if tier not in TIER_DEFAULTS:
        print(f"❌ Invalid tier '{tier}'. Must be T0, T1, or T2")
        sys.exit(1)

    # Generate guard details
    guard_id = f"{guard_type}.{name}"
    function_name = f"{name}_guard"
    tier_info = TIER_DEFAULTS[tier]
    budget_ms = tier_info["budget_ms"]

    if description is None:
        description = f"{name.replace('_', ' ').title()} guard ({tier_info['description']})"

    # Create guard file
    guard_file = output_dir / f"{name}.py"

    if guard_file.exists():
        print(f"❌ Guard file already exists: {guard_file}")
        sys.exit(1)

    # Generate parameters based on type
    if guard_type == "pii":
        params = "types: List[str], mode: str = 'mask'"
        param_docs = "        types: List of PII types to detect (e.g., ['email', 'ssn'])\n        mode: Redaction mode ('mask' or 'hash')"
    elif guard_type == "toxicity":
        params = "threshold: float = 0.7, categories: Optional[List[str]] = None"
        param_docs = "        threshold: Toxicity score threshold (0-1)\n        categories: Specific categories to check"
    elif guard_type == "schema":
        params = "schema: Dict[str, Any]"
        param_docs = "        schema: JSON schema to validate against"
    elif guard_type == "custom":
        params = "config: Dict[str, Any]"
        param_docs = "        config: Custom configuration dictionary"
    else:
        params = "config: Dict[str, Any] = None"
        param_docs = "        config: Guard configuration"

    # Write guard file
    content = GUARD_TEMPLATE.format(
        guard_id=guard_id,
        function_name=function_name,
        description=description,
        tier=tier,
        budget_ms=budget_ms,
        params=params,
        param_docs=param_docs
    )

    guard_file.write_text(content)

    print(f"✅ Created guard: {guard_file}")
    print(f"   Guard ID: {guard_id}")
    print(f"   Tier: {tier} (budget: {budget_ms}ms)")
    print("\n📝 Next steps:")
    print(f"   1. Implement guard logic in {guard_file}")
    print(f"   2. Register in guards/{guard_type}/__init__.py")
    print(f"   3. Test with: heimdall test {guard_id}")


def create_policy(
    name: str,
    guards: str,
    output_dir: Path,
    description: str | None = None
) -> None:
    """Create a new policy file"""

    policy_id = f"{name}_v1"
    policy_file = output_dir / f"{policy_id}.yaml"

    if policy_file.exists():
        print(f"❌ Policy file already exists: {policy_file}")
        sys.exit(1)

    if description is None:
        description = f"{name.replace('_', ' ').title()} policy"

    # Parse guards
    guard_list = [g.strip() for g in guards.split(",")]

    # Generate guard definitions
    guard_defs = []
    guard_seq = []

    for i, guard_id in enumerate(guard_list, 1):
        guard_name = guard_id.replace(".", "_")
        guard_defs.append(f"  - id: {guard_id}")
        guard_defs.append("    target: messages[*].content")
        if i < len(guard_list):
            guard_defs.append("")
        guard_seq.append(guard_name)

    # Write policy file
    content = POLICY_TEMPLATE.format(
        policy_name=name.replace("_", " ").title(),
        policy_id=policy_id,
        description=description,
        guard_definitions="\n".join(guard_defs),
        guard_sequence=", ".join(guard_seq)
    )

    policy_file.write_text(content)

    print(f"✅ Created policy: {policy_file}")
    print(f"   Policy ID: {policy_id}")
    print(f"   Guards: {', '.join(guard_list)}")
    print("\n📝 Next steps:")
    print(f"   1. Customize policy in {policy_file}")
    print(f"   2. Test with: heimdall validate --policy {policy_file}")
    print(f"   3. Deploy with: heimdall deploy {policy_file}")


def create_pack(name: str, output_dir: Path) -> None:
    """Create a new guard pack directory"""

    pack_dir = output_dir / name

    if pack_dir.exists():
        print(f"❌ Pack directory already exists: {pack_dir}")
        sys.exit(1)

    pack_dir.mkdir(parents=True)

    # Create __init__.py
    init_file = pack_dir / "__init__.py"
    init_file.write_text(f'''"""
{name.title()} guard pack
"""

from .guards import *

__all__ = [
    # Add your guard exports here
]
''')

    # Create guards.py template
    guards_file = pack_dir / "guards.py"
    guards_file.write_text('''"""
Guard implementations
"""

from heimdall import guard, Guard, Ctx, Either, Left_, Right_, Violation
from typing import Dict, Any, List


# Add your guards here
''')

    print(f"✅ Created guard pack: {pack_dir}")
    print("   Structure:")
    print(f"   {pack_dir}/")
    print("   ├── __init__.py")
    print("   └── guards.py")
    print("\n📝 Next steps:")
    print(f"   1. Add guards to {guards_file}")
    print(f"   2. Export guards in {init_file}")
    print("   3. Import in your policies")


def main() -> None:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        prog="heimdall-create",
        description="Create guards, policies, and guard packs for Heimdall"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Guard creation
    guard_parser = subparsers.add_parser("guard", help="Create a new guard")
    guard_parser.add_argument("name", help="Guard name (e.g., 'email_detector')")
    guard_parser.add_argument(
        "--type",
        choices=["pii", "toxicity", "schema", "tools", "custom"],
        default="custom",
        help="Guard type/category"
    )
    guard_parser.add_argument(
        "--tier",
        choices=["T0", "T1", "T2"],
        default="T1",
        help="Performance tier (T0=<5ms, T1=5-20ms, T2=20ms+)"
    )
    guard_parser.add_argument(
        "--output",
        type=Path,
        default=Path("./guards"),
        help="Output directory"
    )
    guard_parser.add_argument(
        "--description",
        help="Guard description"
    )

    # Policy creation
    policy_parser = subparsers.add_parser("policy", help="Create a new policy")
    policy_parser.add_argument("name", help="Policy name (e.g., 'enterprise')")
    policy_parser.add_argument(
        "--guards",
        required=True,
        help="Comma-separated guard IDs (e.g., 'pii.email,toxicity.hate')"
    )
    policy_parser.add_argument(
        "--output",
        type=Path,
        default=Path("./policies"),
        help="Output directory"
    )
    policy_parser.add_argument(
        "--description",
        help="Policy description"
    )

    # Pack creation
    pack_parser = subparsers.add_parser("pack", help="Create a new guard pack")
    pack_parser.add_argument("name", help="Pack name (e.g., 'compliance')")
    pack_parser.add_argument(
        "--output",
        type=Path,
        default=Path("./guards"),
        help="Output directory"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "guard":
        create_guard(
            args.name,
            args.type,
            args.tier,
            args.output,
            args.description
        )
    elif args.command == "policy":
        create_policy(
            args.name,
            args.guards,
            args.output,
            args.description
        )
    elif args.command == "pack":
        create_pack(args.name, args.output)


if __name__ == "__main__":
    main()

