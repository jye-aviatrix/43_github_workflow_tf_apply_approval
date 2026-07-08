#!/usr/bin/env python3
"""Evaluate `terraform show -json <plan>` against risk-rules.yaml.

Writes a Markdown report to $GITHUB_STEP_SUMMARY (or stdout as fallback)
and a plain-text digest to risk-report.md.

Exits 0 always — the workflow's approval gate, not this script, decides
whether apply proceeds. Reviewers see the report before approving.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

LEVELS = ["critical", "high", "medium", "low"]
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
LEVEL_ICON = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}


def load_rules(path: Path) -> list[dict]:
    with path.open() as f:
        rules = yaml.safe_load(f) or []
    if not isinstance(rules, list):
        raise SystemExit(f"{path}: expected a YAML list of rules")
    for i, r in enumerate(rules):
        if r.get("level") not in LEVEL_RANK:
            raise SystemExit(f"{path}[{i}]: invalid or missing level")
        if "reason" not in r:
            raise SystemExit(f"{path}[{i}]: missing reason")
    return rules


def changed_attrs(change: dict) -> set[str]:
    before = change.get("before") or {}
    after = change.get("after") or {}
    keys = set(before) | set(after)
    return {k for k in keys if before.get(k) != after.get(k)}


def rule_matches(rule: dict, resource: dict, change: dict) -> bool:
    m = rule.get("match") or {}
    if not m:
        return True
    if "action" in m and m["action"] not in change.get("actions", []):
        return False
    if "resource_type" in m and m["resource_type"] != resource.get("type"):
        return False
    if "resource_address" in m and m["resource_address"] != resource.get("address"):
        return False
    if "attribute_changed" in m and m["attribute_changed"] not in changed_attrs(change):
        return False
    return True


def assess(plan_json: dict, rules: list[dict]) -> list[dict]:
    findings = []
    for rc in plan_json.get("resource_changes", []):
        actions = rc.get("change", {}).get("actions", [])
        if actions == ["no-op"] or actions == ["read"]:
            continue
        matched = [r for r in rules if rule_matches(r, rc, rc.get("change", {}))]
        if not matched:
            continue
        top = min(matched, key=lambda r: LEVEL_RANK[r["level"]])
        findings.append(
            {
                "address": rc.get("address"),
                "type": rc.get("type"),
                "actions": actions,
                "level": top["level"],
                "reason": top["reason"].strip(),
            }
        )
    findings.sort(key=lambda f: (LEVEL_RANK[f["level"]], f["address"]))
    return findings


def render_markdown(findings: list[dict]) -> str:
    lines = ["# Terraform plan risk assessment", ""]
    if not findings:
        lines.append("No resource changes detected (or all changes were no-op / read-only).")
        return "\n".join(lines) + "\n"

    counts = {lvl: 0 for lvl in LEVELS}
    for f in findings:
        counts[f["level"]] += 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Level | Count |")
    lines.append("|---|---|")
    for lvl in LEVELS:
        if counts[lvl]:
            lines.append(f"| {LEVEL_ICON[lvl]} | {counts[lvl]} |")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    lines.append("| Level | Action | Resource | Rationale |")
    lines.append("|---|---|---|---|")
    for f in findings:
        actions = ", ".join(f["actions"])
        reason = f["reason"].replace("\n", " ")
        lines.append(f"| {LEVEL_ICON[f['level']]} | `{actions}` | `{f['address']}` | {reason} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--plan-json", required=True, type=Path)
    p.add_argument("--rules", required=True, type=Path)
    p.add_argument("--report-out", default="risk-report.md", type=Path)
    args = p.parse_args()

    plan_json = json.loads(args.plan_json.read_text())
    rules = load_rules(args.rules)
    findings = assess(plan_json, rules)
    report = render_markdown(findings)

    args.report_out.write_text(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(report)
    else:
        sys.stdout.write(report)

    top = min((LEVEL_RANK[f["level"]] for f in findings), default=len(LEVELS))
    top_level = LEVELS[top] if top < len(LEVELS) else "none"
    print(f"::notice::Highest risk level: {top_level} ({len(findings)} finding(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())