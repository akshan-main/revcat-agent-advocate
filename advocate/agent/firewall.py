"""YAML-based action firewall with eval gates and rollback policy.

Three layers:
  1. Pre-execution rules — block actions before they run
  2. Eval gates — quality thresholds checked after production
  3. Rollback policy — what happens when an eval gate fails

Rules live in firewall.yaml at project root.
"""
import fnmatch
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml


_CONFIG: dict | None = None
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "firewall.yaml"


def _load_config() -> dict:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            _CONFIG = yaml.safe_load(f) or {}
    else:
        _CONFIG = {}
    return _CONFIG


def reload_rules():
    """Force reload from disk."""
    global _CONFIG
    _CONFIG = None
    return _load_config()


# ── Condition Evaluator ──────────────────────────────────────────────

def _eval_condition(cond: str, context: dict) -> bool:
    """Evaluate a condition string against a context dict.

    Supports:
      - "key == value" / "key != value"
      - "key == true/false" (boolean)
      - "key < N" / "key > N" (numeric comparison)
      - "key in [A,B,C] and other_key == value" (compound 'and')
      - "key matches pattern" (fnmatch glob)
      - "key matches pat1 or pat2" (multiple glob patterns)
    """
    if " and " in cond:
        parts = cond.split(" and ")
        return all(_eval_condition(p.strip(), context) for p in parts)

    # "key matches pattern or pattern2"
    match_or = re.match(r"(\w+)\s+matches\s+(.+)", cond)
    if match_or:
        key, patterns_str = match_or.group(1), match_or.group(2)
        val = str(context.get(key, ""))
        return any(fnmatch.fnmatch(val, p.strip()) for p in patterns_str.split(" or "))

    # "key in [A,B,C]"
    in_match = re.match(r"(\w+)\s+in\s+\[([^\]]+)\]", cond)
    if in_match:
        key = in_match.group(1)
        vals = [v.strip() for v in in_match.group(2).split(",")]
        return str(context.get(key, "")) in vals

    # "key < N" / "key > N"
    cmp_match = re.match(r"(\w+)\s*(<|>|<=|>=)\s*(\d+)", cond)
    if cmp_match:
        key, op, threshold = cmp_match.group(1), cmp_match.group(2), int(cmp_match.group(3))
        val = context.get(key, 0)
        try:
            val = int(val) if val is not None else 0
        except (ValueError, TypeError):
            val = 0
        if op == "<":
            return val < threshold
        if op == ">":
            return val > threshold
        if op == "<=":
            return val <= threshold
        if op == ">=":
            return val >= threshold

    # "key == value" / "key != value"
    eq_match = re.match(r"(\w+)\s*(==|!=)\s*(.+)", cond)
    if eq_match:
        key, op, expected = eq_match.group(1), eq_match.group(2), eq_match.group(3).strip().strip("'\"")
        actual = context.get(key)
        if expected.lower() in ("true", "false"):
            expected_bool = expected.lower() == "true"
            return (bool(actual) == expected_bool) if op == "==" else (bool(actual) != expected_bool)
        actual_str = str(actual) if actual is not None else ""
        return (actual_str == expected) if op == "==" else (actual_str != expected)

    return False


# ── Verdict Types ────────────────────────────────────────────────────

class FirewallVerdict:
    """Result of a firewall check."""
    __slots__ = ("allowed", "action", "reason")

    def __init__(self, allowed: bool, action: str, reason: str = ""):
        self.allowed = allowed
        self.action = action
        self.reason = reason

    def __bool__(self):
        return self.allowed

    def __repr__(self):
        status = "ALLOW" if self.allowed else "DENY"
        return f"Firewall({status}: {self.action} — {self.reason})"


class EvalResult:
    """Result of a post-execution eval gate check."""
    __slots__ = ("passed", "gate_name", "failures", "rollback_action")

    def __init__(self, passed: bool, gate_name: str, failures: list[str], rollback_action: str = ""):
        self.passed = passed
        self.gate_name = gate_name
        self.failures = failures
        self.rollback_action = rollback_action

    def __bool__(self):
        return self.passed

    def __repr__(self):
        if self.passed:
            return f"EvalGate(PASS: {self.gate_name})"
        return f"EvalGate(FAIL: {self.gate_name} — {', '.join(self.failures)} → {self.rollback_action})"


# ── Pre-Execution Check ─────────────────────────────────────────────

def check(action: str, context: dict | None = None) -> FirewallVerdict:
    """Check whether an action is allowed under the current firewall rules."""
    ctx = context or {}
    rules = _load_config().get("rules", [])

    for rule in rules:
        if rule.get("action") != action:
            continue

        for cond in rule.get("deny_if", []):
            if _eval_condition(cond, ctx):
                return FirewallVerdict(False, action, f"denied by: {cond}")

        allow_conditions = rule.get("allow_if", [])
        if allow_conditions:
            for cond in allow_conditions:
                if not _eval_condition(cond, ctx):
                    return FirewallVerdict(False, action, f"allow_if not met: {cond}")
            return FirewallVerdict(True, action, "all allow_if conditions met")

    return FirewallVerdict(True, action, "no rule matched")


# ── Post-Execution Eval Gates ───────────────────────────────────────

def eval_content(content_data: dict) -> EvalResult:
    """Evaluate a content piece against quality gates."""
    cfg = _load_config()
    gates = cfg.get("eval_gates", {}).get("content", {})
    rollback = cfg.get("rollback", {}).get("content_below_threshold", {})
    failures = []

    min_cites = gates.get("min_citations", 0)
    if content_data.get("citations_count", 0) < min_cites:
        failures.append(f"citations {content_data.get('citations_count', 0)} < {min_cites}")

    min_words = gates.get("min_word_count", 0)
    if content_data.get("word_count", 0) < min_words:
        failures.append(f"words {content_data.get('word_count', 0)} < {min_words}")

    body = content_data.get("body_md", "")
    for section in gates.get("required_sections", []):
        if f"## {section}" not in body and f"# {section}" not in body:
            failures.append(f"missing section: {section}")

    return EvalResult(
        passed=len(failures) == 0,
        gate_name="content",
        failures=failures,
        rollback_action=rollback.get("action", "quarantine") if failures else "",
    )


def eval_tweet(tweet_data: dict) -> EvalResult:
    """Evaluate a tweet against quality gates."""
    cfg = _load_config()
    gates = cfg.get("eval_gates", {}).get("tweet", {})
    rollback = cfg.get("rollback", {}).get("tweet_rejected_final", {})
    failures = []

    max_chars = gates.get("max_chars", 280)
    text = tweet_data.get("text", "")
    if len(text) > max_chars:
        failures.append(f"length {len(text)} > {max_chars}")

    if gates.get("critic_must_approve") and not tweet_data.get("critic_approved"):
        failures.append("critic did not approve")

    return EvalResult(
        passed=len(failures) == 0,
        gate_name="tweet",
        failures=failures,
        rollback_action=rollback.get("action", "discard") if failures else "",
    )


def eval_feedback(feedback_data: dict) -> EvalResult:
    """Evaluate a feedback item against quality gates."""
    cfg = _load_config()
    gates = cfg.get("eval_gates", {}).get("feedback", {})
    failures = []

    if gates.get("must_have_repro_steps") and not feedback_data.get("repro_steps"):
        failures.append("missing repro steps")

    if gates.get("must_have_proposed_fix") and not feedback_data.get("proposed_fix"):
        failures.append("missing proposed fix")

    return EvalResult(
        passed=len(failures) == 0,
        gate_name="feedback",
        failures=failures,
        rollback_action="quarantine" if failures else "",
    )


# ── Rollback Executor ───────────────────────────────────────────────

def execute_rollback(eval_result: EvalResult, db_conn=None, content_id: int | None = None) -> str:
    """Execute rollback policy for a failed eval gate.

    Returns a human-readable summary of what was done.
    """
    if eval_result.passed:
        return "No rollback needed — eval passed."

    action = eval_result.rollback_action
    summary_parts = [f"Eval gate '{eval_result.gate_name}' FAILED: {', '.join(eval_result.failures)}"]

    if action == "quarantine" and db_conn and content_id:
        try:
            db_conn.execute(
                "UPDATE content_pieces SET status = 'quarantined' WHERE id = ?",
                (content_id,),
            )
            db_conn.commit()
            summary_parts.append(f"Content ID {content_id} quarantined.")
        except Exception as e:
            summary_parts.append(f"Quarantine failed: {e}")

    elif action == "discard":
        summary_parts.append("Draft discarded (not posted).")

    elif action == "revert_site":
        summary_parts.append("Site revert triggered — rebuild from last known-good state.")

    # Log to ledger if available
    if db_conn:
        try:
            from ..db import insert_row, now_iso
            insert_row(db_conn, "run_log", {
                "run_id": f"rollback_{eval_result.gate_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                "sequence": 0,
                "command": "rollback",
                "started_at": now_iso(),
                "ended_at": now_iso(),
                "inputs": f'{{"gate": "{eval_result.gate_name}", "failures": {eval_result.failures}}}',
                "success": 1,
            })
        except Exception:
            pass

    return " | ".join(summary_parts)


# ── Report ───────────────────────────────────────────────────────────

def generate_report(db_conn=None) -> dict:
    """Generate a firewall status report for the scorecard."""
    cfg = _load_config()
    rules = cfg.get("rules", [])
    gates = cfg.get("eval_gates", {})
    rollback = cfg.get("rollback", {})

    report = {
        "rules_count": len(rules),
        "rules": [{"action": r["action"], "type": "allow_if" if "allow_if" in r else "deny_if"} for r in rules],
        "eval_gates": list(gates.keys()),
        "rollback_policies": list(rollback.keys()),
    }

    if db_conn:
        try:
            from ..db import query_rows
            rollbacks = query_rows(db_conn, "run_log", where={"command": "rollback"})
            report["rollbacks_executed"] = len(rollbacks)
        except Exception:
            report["rollbacks_executed"] = 0

    return report
