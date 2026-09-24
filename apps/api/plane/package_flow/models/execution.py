# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runner, claim and run models (FR-G03..FR-G07, INV-01, INV-04, INV-09).

Customer code never executes in the Plane web/API/live process; these rows
only coordinate an external runner that connects outbound.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from .base import ExtensionBaseModel, IssueScopedModel


class RunnerProfile(ExtensionBaseModel):
    """A registered external runner (local, customer-hosted or managed; O01)."""

    class Kind(models.TextChoices):
        LOCAL = "local", "Developer machine"
        CUSTOMER = "customer", "Customer-hosted runner"
        MANAGED = "managed", "Managed runner"

    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.LOCAL)
    # Responsible human Plane user; the runner acts as an *agent* principal.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=12)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    policy = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_runner_profiles"


class Claim(IssueScopedModel):
    """Atomic exclusive (or explicitly collaborative) claim with lease + fencing (FR-G04)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    repository_binding = models.ForeignKey(
        "package_flow.RepositoryBinding", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # Unit key: issue + binding (or "none" for non-repo packages) — used for the exclusive constraint.
    unit_key = models.CharField(max_length=128)
    exclusive = models.BooleanField(default=True)
    holder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    runner = models.ForeignKey(RunnerProfile, on_delete=models.CASCADE, null=True, blank=True, related_name="claims")
    approval = models.ForeignKey(
        "package_flow.ExecutionApproval", on_delete=models.PROTECT, null=True, blank=True, related_name="claims"
    )
    fencing_token = models.BigIntegerField()
    lease_expires_at = models.DateTimeField()
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pf_claims"
        constraints = [
            # At most one active exclusive claim per unit — enforced by the database (AC05).
            models.UniqueConstraint(
                fields=["unit_key"],
                condition=Q(status="active", exclusive=True, deleted_at__isnull=True),
                name="pf_claim_one_active_exclusive",
            )
        ]


class FencingCounter(models.Model):
    """Monotonic fencing sequence per claim unit."""

    unit_key = models.CharField(max_length=128, primary_key=True)
    value = models.BigIntegerField(default=0)

    class Meta:
        db_table = "pf_fencing_counters"


class ExecutionRun(IssueScopedModel):
    """One controlled execution bound to exact revision, approval and claim (INV-01/04)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        CLAIMED = "claimed", "Claimed"
        RUNNING = "running", "Running"
        WAITING = "waiting", "Waiting"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        FINISHED = "finished", "Finished"

    revision = models.ForeignKey("package_flow.PackageRevision", on_delete=models.PROTECT, related_name="runs")
    approval = models.ForeignKey("package_flow.ExecutionApproval", on_delete=models.PROTECT, related_name="runs")
    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="runs")
    runner = models.ForeignKey(RunnerProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="runs")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    mode = models.CharField(max_length=16, default="human")  # human | agent
    agent_adapter = models.CharField(max_length=64, blank=True, default="")
    base_commits = models.JSONField(default=dict, blank=True)
    limits = models.JSONField(default=dict, blank=True)
    spend_minor = models.BigIntegerField(default=0)
    run_token_hash = models.CharField(max_length=64, blank=True, default="")
    run_token_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    pause_reason = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "pf_execution_runs"
        ordering = ("-created_at",)


class RunAction(IssueScopedModel):
    """Controlled runner action log (push, commit, check …), fenced (AC06, FR-G06)."""

    run = models.ForeignKey(ExecutionRun, on_delete=models.CASCADE, related_name="actions")
    action = models.CharField(max_length=32)
    fencing_token = models.BigIntegerField()
    accepted = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_run_actions"
        ordering = ("created_at",)
