# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""NFR-01 probe: server-side p95 of critical list/detail reads.

Runs in-process through Django's test client (no network, no provider/model
time) against a workspace seeded by ``package_flow_seed_load_profile``. Prints
p50/p95 per endpoint and the data volume. Results are only meaningful together
with the stated scale and machine; they are not an SLA (PRD §16).
"""

import statistics
import time

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import override_settings

from plane.db.models import Issue, Project, Workspace
from plane.package_flow.models import DomainEvent, Message, PackageProfile


class Command(BaseCommand):
    help = "Measure server-side latency of critical Project Hub reads (NFR-01)"

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="workspace slug seeded by package_flow_seed_load_profile")
        parser.add_argument("--iterations", type=int, default=30)

    @override_settings(ALLOWED_HOSTS=["*"])
    def handle(self, *args, **opts):
        ws = Workspace.objects.get(slug=opts["slug"])
        owner = ws.owner
        project = Project.objects.filter(workspace=ws).order_by("created_at").first()
        issue = Issue.objects.filter(project=project).first()
        client = Client()
        client.force_login(owner)
        p = f"/api/workspaces/{ws.slug}/projects/{project.id}/package-flow"
        w = f"/api/workspaces/{ws.slug}/package-flow"
        endpoints = {
            "package list": f"{p}/packages/?view=all",
            "package status": f"{p}/work-items/{issue.id}/status",
            "project overview": f"{p}/overview",
            "activity (7d)": f"{p}/activity/?since=2000-01-01T00:00:00Z",
            "roadmap": f"{w}/roadmap/",
            "search": f"{w}/search/?q=package",
        }
        self.stdout.write(
            f"volume: projects={Project.objects.filter(workspace=ws).count()} "
            f"packages={PackageProfile.objects.filter(workspace=ws).count()} "
            f"messages={Message.objects.filter(workspace=ws).count()} "
            f"events={DomainEvent.objects.filter(workspace=ws).count()}"
        )
        for name, url in endpoints.items():
            client.get(url)  # warm-up
            samples, status = [], None
            for _ in range(opts["iterations"]):
                t0 = time.perf_counter()
                resp = client.get(url)
                samples.append((time.perf_counter() - t0) * 1000)
                status = resp.status_code
            samples.sort()
            p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
            self.stdout.write(f"{name:18s} status={status} p50={statistics.median(samples):7.1f}ms p95={p95:7.1f}ms")
