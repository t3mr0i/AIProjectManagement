# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Seed the local stack for the Project Hub browser test (tools/project-hub/e2e/run.sh).

Run with: python manage.py shell < tools/project-hub/e2e/seed.py
Idempotent for the instance, user, workspace and project (fixed e-mail / slug); every run
creates a *fresh* work item so "activate as work package" can be exercised again. Writes the
ids the browser script needs to $E2E_SEED_OUT (default /tmp/project-hub-e2e-seed.json).
All data is synthetic.
"""
import json
import os
import uuid

from django.utils import timezone

from plane.db.models import FileAsset, Issue, Profile, Project, ProjectMember, State, User, Workspace, WorkspaceMember
from plane.license.models import Instance
from plane.package_flow.models import Capability, CapabilityGrant, ExtensionActivation, UploadRecord
from plane.package_flow.services import knowledge

EMAIL = os.environ.get("E2E_EMAIL", "project-hub-e2e@example.test")
PASSWORD = os.environ.get("E2E_PASSWORD", "Ph-e2e-Passw0rd!")
SLUG = os.environ.get("E2E_WORKSPACE", "ph-e2e")
OUT = os.environ.get("E2E_SEED_OUT", "/tmp/project-hub-e2e-seed.json")

# Instance must be set up, otherwise the web app shows the instance setup screen.
if not Instance.objects.exists():
    Instance.objects.create(
        instance_name="Project Hub e2e",
        instance_id=uuid.uuid4().hex,
        current_version="e2e",
        latest_version="e2e",
        last_checked_at=timezone.now(),
        is_setup_done=True,
        is_signup_screen_visited=True,
        is_verified=True,
        is_telemetry_enabled=False,
        is_support_required=False,
    )
else:
    Instance.objects.update(is_setup_done=True, is_signup_screen_visited=True)

user = User.objects.filter(email=EMAIL).first()
if user is None:
    user = User.objects.create(
        email=EMAIL, username=uuid.uuid4().hex[:12], first_name="Hub", last_name="Tester", display_name="hubtester"
    )
user.set_password(PASSWORD)
user.is_active = True
user.is_password_autoset = False
user.save()

workspace = Workspace.objects.filter(slug=SLUG).first()
if workspace is None:
    workspace = Workspace.objects.create(name="Project Hub e2e", slug=SLUG, owner=user)
WorkspaceMember.objects.get_or_create(workspace=workspace, member=user, defaults={"role": 20})

profile, _ = Profile.objects.get_or_create(user=user)
profile.is_onboarded = True
profile.is_tour_completed = True
profile.last_workspace_id = workspace.id
profile.onboarding_step = {
    "profile_complete": True,
    "workspace_create": True,
    "workspace_invite": True,
    "workspace_join": True,
}
profile.save()

project = Project.objects.filter(workspace=workspace, identifier="PHE").first()
if project is None:
    project = Project.objects.create(name="Hub Demo", identifier="PHE", workspace=workspace, created_by=user)
ProjectMember.objects.get_or_create(project=project, workspace=workspace, member=user, defaults={"role": 20})
state = State.objects.filter(project=project, group="unstarted").first() or State.objects.create(
    name="Todo", group="unstarted", project=project, workspace=workspace, default=True
)

# Extension on for workspace + project, all business capabilities granted workspace-wide.
ExtensionActivation.objects.update_or_create(
    workspace=workspace, project=None, defaults={"is_enabled": True, "changed_by": user}
)
ExtensionActivation.objects.update_or_create(
    workspace=workspace, project=project, defaults={"is_enabled": True, "changed_by": user}
)
for cap in Capability:
    CapabilityGrant.objects.get_or_create(
        workspace=workspace, project=None, member=user, capability=cap.value, deleted_at__isnull=True
    )

issue = Issue.objects.create(
    name=f"Export CSV for invoices ({timezone.now():%H:%M:%S})",
    project=project,
    workspace=workspace,
    state=state,
    description_html="<p>Customers need a CSV export of their invoices.</p>",
    created_by=user,
)



def attachment(name, mime, size, target_issue):
    return FileAsset.objects.create(
        attributes={"name": name, "type": mime, "size": size},
        asset=f"{workspace.id}/e2e-{uuid.uuid4().hex}-{name}",
        workspace=workspace,
        project=project,
        issue=target_issue,
        entity_type="ISSUE_ATTACHMENT",
        entity_identifier=str(target_issue.id),
        size=size,
        is_uploaded=True,
        created_by=user,
    )


# Registered uploads in three scan states. Object storage is not needed: content is passed to
# the scanner directly (clean text, EICAR test signature → quarantined).
if not UploadRecord.objects.filter(project=project).exists():
    notes = attachment("release-notes.md", "text/markdown", 64, issue)
    knowledge.register(user, project, notes.id, content=b"# Release notes\n\nCSV export for invoices.\n")
    bad = attachment("invoice-scan.txt", "text/plain", 68, issue)
    knowledge.register(user, project, bad.id, content=knowledge.EICAR)
# A fresh unregistered attachment for the "register" flow in the UI (no stored bytes → scan pending).
attachment(f"requirements-{timezone.now():%H%M%S}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 18432, issue)

data = {
    "email": EMAIL,
    "password": PASSWORD,
    "workspace_slug": workspace.slug,
    "project_id": str(project.id),
    "project_identifier": project.identifier,
    "issue_id": str(issue.id),
    "issue_sequence": issue.sequence_id,
}
with open(OUT, "w") as fh:
    json.dump(data, fh)
print("project hub e2e seed:", json.dumps(data))
