# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI evaluation set (PRD §14.5) — see docs/project-hub/AI_EVALUATION.md.

Ten fixed situations. Assertions check *decisions* (question type, source
status, allowed action, flags), never wording. By default the deterministic
``RuleBasedProvider`` runs; set ``PACKAGE_FLOW_AI_EVAL_PROVIDER=configured``
to evaluate the provider configured through ``LLM_API_KEY``/``LLM_MODEL``.
"""

import os

import pytest

from plane.package_flow.ai import clarify
from plane.package_flow.ai.context import assemble_context, projects_audience
from plane.package_flow.ai.provider import STATEMENT_STATUSES, RuleBasedProvider, get_provider
from plane.package_flow.models import (
    Conversation,
    ConversationParticipant,
    Decision,
    ExecutionApproval,
    Message,
    PackageProfile,
)


def eval_provider():
    if os.environ.get("PACKAGE_FLOW_AI_EVAL_PROVIDER", "").lower() == "configured":
        return get_provider()
    return RuleBasedProvider()


def run(task, question, contexts):
    messages = [{"role": "user", "content": question}]
    messages += [{"role": "context", "content": text, "source": src} for src, text in contexts]
    result = eval_provider().complete(task, messages)
    assert result.ok, result.error
    # Invariants for every situation: only proposals, labelled statements.
    assert result.allowed_actions == ["propose"]
    assert all(s.status in STATEMENT_STATUSES for s in result.statements)
    return result


def kinds(result):
    return {f["kind"] for f in result.flags}


def setup(world):
    alice, bob, carol = world.member(), world.member(), world.member()
    project = world.project(identifier="EVL", members=[(alice, 15), (bob, 15), (carol, 15)])
    world.enable(project)
    return project, alice, bob, carol


@pytest.mark.unit
class TestAIEvaluation:
    def test_s01_incomplete_brief_asks_outcome_first(self, world):
        project, alice, _, _ = setup(world)
        issue = world.issue(project, name="Improve reports")
        PackageProfile.objects.create(issue=issue)
        step = clarify.step(issue, alice)
        assert step["type"] == "question" and step["topic"] == "outcome"
        assert step["recommendation"]["status"] == "proposed"
        result = run("concretize", "Improve reports", [({"type": "issue", "id": str(issue.id)}, issue.name)])
        assert any(s.status == "proposed" for s in result.statements)
        # Allowed action: propose only — nothing applied, nothing approved.
        assert PackageProfile.objects.get(issue=issue).version == 1
        assert not ExecutionApproval.objects.exists()

    def test_s02_answer_already_in_project_is_used(self, world):
        project, alice, _, _ = setup(world)
        d = Decision.objects.create(workspace=world.workspace, project=project, title="Export format",
                                    text="The export format is CSV.", status="confirmed", confirmed_by=alice)
        issue = world.issue(project, name="Export", description_html="<p>Export format: TBD.</p>")
        PackageProfile.objects.create(issue=issue, outcome="o", non_goals=["n"], criteria=[{"text": "c"}],
                                      risk={"r": 1})
        open_qs = [q for q in clarify.candidate_questions(issue) if "answered_by" not in q]
        assert all("export" not in q["question"].lower() for q in open_qs)
        result = run("answer", "Which export format do we use?",
                     [({"type": "decision", "id": str(d.id), "confirmed": True}, f"{d.title}: {d.text}")])
        assert any(s.status == "confirmed" and s.sources and s.sources[0]["id"] == str(d.id)
                   for s in result.statements)
        assert not result.needs_clarification

    def test_s03_contradictory_documents_create_clarification(self, world):
        result = run("answer", "Which export format should we use?", [
            ({"type": "page", "id": "p1"}, "Spec v1: The export format is CSV."),
            ({"type": "page", "id": "p2"}, "Spec v2: The export format is XLSX."),
        ])
        assert "contradiction" in kinds(result) and result.needs_clarification
        assert not any(s.status == "confirmed" for s in result.statements)  # no silent choice
        assert any(s.status == "proposed" for s in result.statements)

    def test_s04_unknown_original_intent_is_not_invented(self, world):
        result = run("answer", "Why does the exporter skip archived rows?", [
            ({"type": "code", "id": "src/export.py", "path": "src/export.py"},
             "def export(rows): return [r for r in rows if not r.archived]  # exporter skips archived rows"),
        ])
        assert "unknown_intent" in kinds(result) and result.needs_clarification
        assert not any(s.status == "confirmed" for s in result.statements)
        code_statements = [s for s in result.statements if s.sources and s.sources[0].get("type") == "code"]
        assert all(s.status in ("observed", "inferred") for s in code_statements)

    def test_s05_layout_only_diagram_change_creates_no_requirement(self, world):
        from plane.package_flow.services import diagrams

        semantic = diagrams.normalize_semantic({"nodes": [{"id": "a", "type": "service", "label": "API"},
                                                          {"id": "b", "type": "db", "label": "DB"}], "edges": []})
        diff = diagrams.semantic_diff(semantic, semantic)
        assert diagrams.is_empty_semantic_diff(diff)
        assert diagrams.layout_diff({"a": {"x": 0, "y": 0}}, {"a": {"x": 50, "y": 0}})["changed"]
        interpretation = diagrams.interpret(diff, semantic)
        assert interpretation["suggested_criteria"] == [] and interpretation["questions"] == []

    def test_s06_semantic_change_needs_confirmation(self, world):
        from plane.package_flow.services import diagrams

        before = diagrams.normalize_semantic({"nodes": [{"id": "a", "type": "service", "label": "API"},
                                                        {"id": "b", "type": "db", "label": "DB"}], "edges": []})
        after = diagrams.normalize_semantic({"nodes": before["nodes"], "edges": [
            {"id": "e1", "source": "a", "target": "b", "type": "writes"},
            {"id": "e2", "source": "b", "target": "a"},
        ]})
        interpretation = diagrams.interpret(diagrams.semantic_diff(before, after), after)
        assert interpretation["suggested_criteria"]
        assert all(c["status"] == "proposed" for c in interpretation["suggested_criteria"])
        assert [q["edge_id"] for q in interpretation["questions"]] == ["e2"]  # ambiguous -> question

    def test_s07_private_source_is_blocked_for_larger_audience(self, world):
        project, alice, bob, _carol = setup(world)
        dm = Conversation.objects.create(workspace=world.workspace, kind="direct", dm_key="k-eval")
        for u in (alice, bob):
            ConversationParticipant.objects.create(conversation=dm, member=u)
        msg = Message.objects.create(conversation=dm, workspace=world.workspace, author=alice, body="secret terms")
        ctx = assemble_context(requester=alice, workspace_id=world.workspace.id,
                               audience_ids=projects_audience([project.id]),
                               selection=[{"type": "message", "id": str(msg.id)}])
        assert ctx.allowed == [] and ctx.blocked[0]["reason"] == "private_source"
        ctx_dm = assemble_context(requester=alice, workspace_id=world.workspace.id, audience_ids={str(bob.id)},
                                  selection=[{"type": "message", "id": str(msg.id)}])
        assert len(ctx_dm.allowed) == 1

    def test_s08_commit_claim_is_not_evidence(self, world):
        result = run("report", "Summarize the test status", [
            ({"type": "commit", "id": "abc123"}, "fix export; all tests passed"),
        ])
        assert "unverified_claim" in kinds(result)
        commit_statements = [s for s in result.statements if s.sources and s.sources[0].get("type") == "commit"]
        assert commit_statements and all(s.status == "observed" for s in commit_statements)

    def test_s09_missing_test_keeps_criterion_unproven(self, world):
        result = run("report", "Is the package verified?", [
            ({"type": "criterion", "id": "AC-1"}, "Export contains only permitted rows"),
            ({"type": "criterion", "id": "AC-2"}, "Export finishes in 5s"),
            ({"type": "criterion", "id": "AC-3"}, "CSV has a header"),
            ({"type": "evidence", "id": "e2", "criterion_id": "AC-2", "result": "passed",
              "trust": "local_self_report"}, "perf ok (local)"),
            ({"type": "evidence", "id": "e3", "criterion_id": "AC-3", "result": "passed", "trust": "provider_ci"},
             "header test passed in CI"),
        ])
        missing = {f["criterion_id"] for f in result.flags if f["kind"] == "missing_evidence"}
        assert missing == {"AC-1", "AC-2"}

    def test_s10_scope_change_during_run_requires_new_approval(self, world):
        result = run("report", "Can the run continue with the new scope?", [
            ({"type": "run", "id": "run-1", "revision_id": "rev-1"}, "Run started on revision 1"),
            ({"type": "revision", "id": "rev-2", "current": True}, "Revision 2 adds PDF export"),
        ])
        flag = next(f for f in result.flags if f["kind"] == "scope_change_requires_new_approval")
        assert flag["current_revision_id"] == "rev-2" and flag["run_revision_ids"] == ["rev-1"]
        assert result.allowed_actions == ["propose"]
        assert not ExecutionApproval.objects.exists()
