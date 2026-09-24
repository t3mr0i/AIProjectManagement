# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Seed PRD §16 "Testprofil A" (scalable) for NFR measurements.

Full profile: 50 projects, 10,000 packages, 100,000 messages, 1,000,000 events,
100 users with realistic (non-public) membership distribution. ``--scale``
shrinks every count proportionally for local runs. All rows are marked as
fixtures (``is_fixture`` on events, ``[load]`` prefixes) and created in a
dedicated workspace so they never mix with real data.
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from plane.db.models import Issue, Project, ProjectMember, State, User, Workspace, WorkspaceMember
from plane.package_flow.models import (
    Conversation,
    ConversationParticipant,
    DomainEvent,
    ExtensionActivation,
    Message,
    PackageProfile,
)

FULL = {"projects": 50, "packages": 10_000, "messages": 100_000, "events": 1_000_000, "users": 100}
BATCH = 5_000


class Command(BaseCommand):
    help = "Seed the NFR load profile (Testprofil A) into a dedicated fixture workspace"

    def add_arguments(self, parser):
        parser.add_argument("--scale", type=float, default=0.01, help="1.0 = full Testprofil A")
        parser.add_argument("--slug", default="load-profile-a")
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **opts):
        rnd = random.Random(opts["seed"])
        n = {k: max(1, int(v * opts["scale"])) for k, v in FULL.items()}
        n["projects"] = max(2, n["projects"])
        n["users"] = max(4, n["users"])
        now = timezone.now()

        with transaction.atomic():
            owner = User.objects.create(email=f"load-owner-{uuid.uuid4().hex[:6]}@example.test", username=uuid.uuid4().hex[:12])
            ws = Workspace.objects.create(name="[load] Testprofil A", slug=f"{opts['slug']}-{uuid.uuid4().hex[:4]}", owner=owner)
            users = [owner] + [
                User(email=f"load-{i}-{uuid.uuid4().hex[:6]}@example.test", username=uuid.uuid4().hex[:12])
                for i in range(n["users"] - 1)
            ]
            User.objects.bulk_create(users[1:])
            WorkspaceMember.objects.bulk_create(
                [WorkspaceMember(workspace=ws, member=u, role=20 if u is owner else 15) for u in users]
            )
            ExtensionActivation.objects.create(workspace=ws, is_enabled=True)

            projects, states = [], {}
            for i in range(n["projects"]):
                p = Project.objects.create(name=f"[load] P{i}", identifier=f"L{i:03d}", workspace=ws)
                projects.append(p)
                states[p.id] = State.objects.create(name="Todo", group="unstarted", project=p, workspace=ws)
                # Realistic ACL: each user sees ~30 % of projects; owner sees all.
                members = [owner] + [u for u in users[1:] if rnd.random() < 0.3]
                ProjectMember.objects.bulk_create(
                    [ProjectMember(project=p, workspace=ws, member=u, role=20 if u is owner else 15) for u in members]
                )

        issues = []
        for i in range(n["packages"]):
            p = projects[i % len(projects)]
            issues.append(
                Issue(name=f"[load] package {i}", project=p, workspace=ws, state=states[p.id], sequence_id=i + 1)
            )
        for chunk in _chunks(issues):
            Issue.objects.bulk_create(chunk)
        for chunk in _chunks(issues):
            PackageProfile.objects.bulk_create(
                [PackageProfile(issue=x, project_id=x.project_id, workspace=ws, intent="load") for x in chunk]
            )

        convs = [Conversation.objects.create(workspace=ws, project=p, kind="project", title="general") for p in projects]
        for c in convs:
            members = ProjectMember.objects.filter(project_id=c.project_id).values_list("member_id", flat=True)
            ConversationParticipant.objects.bulk_create([ConversationParticipant(conversation=c, member_id=m) for m in members])
        msgs = [
            Message(conversation=convs[i % len(convs)], workspace=ws, author=owner, body=f"[load] message {i}")
            for i in range(n["messages"])
        ]
        for chunk in _chunks(msgs):
            Message.objects.bulk_create(chunk)

        types = ["ci.check.observed", "git.commit.observed", "run.progress", "git.merge.observed", "deployment.observed"]
        created = 0
        while created < n["events"]:
            batch = []
            for _ in range(min(BATCH, n["events"] - created)):
                issue = issues[rnd.randrange(len(issues))]
                t = now - timedelta(minutes=rnd.randrange(60 * 24 * 90))
                batch.append(
                    DomainEvent(
                        workspace=ws, project_id=issue.project_id, issue=issue, event_type=rnd.choice(types),
                        aggregate_type="package", aggregate_id=issue.id, occurred_at=t, received_at=t,
                        correlation_id=uuid.uuid4(), deduplication_key=f"load:{uuid.uuid4()}", source_kind="provider",
                        source_id="load", source_instance_id="load", actor_kind="system", actor_id="load",
                        is_fixture=True, summary="[load] fixture event",
                    )
                )
            DomainEvent.objects.bulk_create(batch)
            created += len(batch)
        self.stdout.write(f"seeded workspace {ws.slug}: {n}")


def _chunks(items):
    for i in range(0, len(items), BATCH):
        yield items[i : i + BATCH]
