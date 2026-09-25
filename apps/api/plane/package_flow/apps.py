# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class PackageFlowConfig(AppConfig):
    name = "plane.package_flow"
    label = "package_flow"
    verbose_name = "Project Hub package flow"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Register native-mutation hooks (FR-B06) and capability checks.
        from . import signals  # noqa: F401

        _allow_idempotency_header()


def _allow_idempotency_header():
    """Let browsers send ``Idempotency-Key`` cross-origin (web and API on different origins).

    Additive: extends the native CORS allow-list instead of editing the core settings module.
    django-cors-headers reads ``settings.CORS_ALLOW_HEADERS`` per request.
    """
    from django.conf import settings

    headers = list(getattr(settings, "CORS_ALLOW_HEADERS", []) or [])
    if "idempotency-key" not in {h.lower() for h in headers}:
        settings.CORS_ALLOW_HEADERS = [*headers, "idempotency-key"]
