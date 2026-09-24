# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared bases for package-flow extension models.

All extension rows reference native Plane identities (Workspace, Project, Issue,
User). ``workspace`` on project-scoped rows is always derived from the project
and never accepted from the client (Vertrag 1.1, PRD §7.1).
"""

from django.db import models

from plane.db.models.base import BaseModel


class ExtensionBaseModel(BaseModel):
    """Workspace-scoped extension row (project optional)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+", null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.project_id:
            # Scope is derived from the native project, never trusted from input.
            self.workspace_id = self.project.workspace_id
        super().save(*args, **kwargs)


class IssueScopedModel(BaseModel):
    """Row bound to exactly one native Issue; project/workspace derived from it."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # The native issue is the single source of project/workspace scope (FR-B02).
        self.project_id = self.issue.project_id
        self.workspace_id = self.issue.workspace_id
        super().save(*args, **kwargs)
