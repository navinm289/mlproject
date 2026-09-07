"""Bounded recursive policy interpreter. No eval, I/O, or mutable state."""
import json

def evaluate_policy(document, tags):
    """Returns match/error; malformed policies must be quarantined, never default-pass."""
    try:
        if document is None or len(document) > 8192:
            raise ValueError("missing_or_oversize_policy")
        tree = json.loads(document)
        available = set(tags or [])
        budget = [0]
        def walk(node, depth=0):
            budget[0] += 1
            if depth > 16 or budget[0] > 256 or not isinstance(node, dict) or len(node) != 1:
                raise ValueError("invalid_policy_structure")
            op, value = next(iter(node.items()))
            if op == "tag" and isinstance(value, str):
                return value.lower().strip() in available
            if op == "not":
                return not walk(value, depth + 1)
            if op in ("all", "any") and isinstance(value, list) and value:
                # Evaluate every branch so an invalid branch cannot hide behind short-circuiting.
                values = [walk(v, depth + 1) for v in value]
                return all(values) if op == "all" else any(values)
            raise ValueError("invalid_policy_operator")
        return (walk(tree), None)
    except (ValueError, TypeError, RecursionError):
        return (False, "invalid_risk_policy")
