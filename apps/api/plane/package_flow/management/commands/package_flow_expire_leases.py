# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Mark claims with an expired lease as ``expired`` and their runs as stale (FR-G04, FR-G07)."""

from django.core.management.base import BaseCommand

from plane.package_flow.services.execution import expire_leases


class Command(BaseCommand):
    help = "Expire Project Hub claims whose lease ran out."

    def handle(self, *args, **options):
        self.stdout.write(f"expired_claims: {expire_leases()}")
