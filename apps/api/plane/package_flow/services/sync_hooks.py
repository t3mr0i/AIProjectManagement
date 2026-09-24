# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Native Issue → external tracker push for platform-owned fields (I12, FR-I03, FR-I05).

A change of the native ``name`` (→ ``title``) or ``priority`` on an issue that
has a package-representing ``ExternalLink`` is pushed to the tracker when that
field is platform-owned. Saves that *apply* an external value are marked with
``_pf_sync_origin`` and never pushed back (no sync loop). ``QuerySet.update``
bypasses signals and therefore does not push; reconciliation does not
re-derive such writes (documented limit).
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from plane.db.models import Issue

logger = logging.getLogger("plane.package_flow.sync")

_OLD = "_pf_sync_old"
_FIELD_MAP = {"name": "title", "priority": "priority"}


@receiver(pre_save, sender=Issue, dispatch_uid="pf_sync_issue_pre_save")
def issue_sync_pre_save(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    try:
        from plane.package_flow.models import ExternalLink

        if not ExternalLink.objects.filter(
            issue_id=instance.pk, object_type="issue", represents_package=True, deleted_at__isnull=True
        ).exists():
            return
        setattr(instance, _OLD, Issue.all_objects.filter(pk=instance.pk).values("name", "priority").first())
    except Exception:  # noqa: BLE001 - never break native writes
        logger.exception("package_flow sync pre_save failed")


@receiver(post_save, sender=Issue, dispatch_uid="pf_sync_issue_post_save")
def issue_sync_post_save(sender, instance, created=False, raw=False, **kwargs):
    old = getattr(instance, _OLD, None)
    origin = getattr(instance, "_pf_sync_origin", None)
    for attr in (_OLD, "_pf_sync_origin"):
        if hasattr(instance, attr):
            delattr(instance, attr)
    if raw or created or not old or origin:
        return
    changed = {
        canonical: getattr(instance, attr)
        for attr, canonical in _FIELD_MAP.items()
        if old.get(attr) != getattr(instance, attr)
    }
    if not changed:
        return
    try:
        from .integrations import push_platform_fields

        push_platform_fields(instance, changed)
    except Exception:  # noqa: BLE001
        logger.exception("package_flow outbound sync failed")
