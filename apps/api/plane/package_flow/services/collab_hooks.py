# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Collaboration hooks: DomainEvent -> notifications (FR-C07).

Runs inside the emitting transaction but in its own savepoint, so a failing
notification never breaks or rolls back the business change / outbox row.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import DomainEvent

logger = logging.getLogger("plane.package_flow.collab_hooks")


@receiver(post_save, sender=DomainEvent, dispatch_uid="package_flow_notify_for_event")
def _notify_on_domain_event(sender, instance, created, **kwargs):
    if not created or instance.is_fixture:
        return
    from .notifications import notify_for_event

    try:
        with transaction.atomic():
            notify_for_event(instance)
    except Exception:  # never break the event store
        logger.exception("notification derivation failed for event %s", instance.id)
