# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Seed a representative *native* Plane dataset (no extension rows) for PF04.

Run with: python manage.py shell < tools/project-hub/seed_native_fixture.py
Creates 2 workspaces, 3 projects, states, 60 issues (incl. drafts, archived,
sub-issues), cycles, modules, pages and relations. All synthetic.
"""
import uuid

from django.utils import timezone

from plane.db.models import (Cycle, CycleIssue, Issue, IssueRelation, Module, ModuleIssue, Page, Project,
                             ProjectMember, ProjectPage, State, User, Workspace, WorkspaceMember)

for w in range(2):
    owner = User.objects.create(email=f"mig-{w}-{uuid.uuid4().hex[:6]}@example.test", username=uuid.uuid4().hex[:12])
    ws = Workspace.objects.create(name=f"Legacy {w}", slug=f"legacy-{w}-{uuid.uuid4().hex[:4]}", owner=owner)
    WorkspaceMember.objects.create(workspace=ws, member=owner, role=20)
    for p in range(2 if w == 0 else 1):
        proj = Project.objects.create(name=f"Legacy P{p}", identifier=f"LG{w}{p}", workspace=ws)
        ProjectMember.objects.create(project=proj, workspace=ws, member=owner, role=20)
        todo = State.objects.create(name="Todo", group="unstarted", project=proj, workspace=ws)
        done = State.objects.create(name="Done", group="completed", project=proj, workspace=ws)
        cycle = Cycle.objects.create(name="Sprint 1", project=proj, workspace=ws, owned_by=owner)
        module = Module.objects.create(name="Module A", project=proj, workspace=ws)
        page = Page.objects.create(name="Spec", workspace=ws, owned_by=owner, description_html="<p>legacy page</p>")
        ProjectPage.objects.create(project=proj, page=page, workspace=ws)
        issues = []
        for i in range(20):
            issue = Issue.objects.create(
                name=f"Legacy issue {i}", project=proj, workspace=ws, state=done if i % 5 == 0 else todo,
                is_draft=(i % 7 == 0), description_html=f"<p>desc {i}</p>",
                parent=issues[0] if i in (3, 4) and issues else None,
                archived_at=timezone.now().date() if i == 19 else None,
            )
            issues.append(issue)
        CycleIssue.objects.create(cycle=cycle, issue=issues[1], project=proj, workspace=ws)
        ModuleIssue.objects.create(module=module, issue=issues[2], project=proj, workspace=ws)
        IssueRelation.objects.create(issue=issues[5], related_issue=issues[6], relation_type="blocked_by", project=proj, workspace=ws)
print("native fixture seeded")
