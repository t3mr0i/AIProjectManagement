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
