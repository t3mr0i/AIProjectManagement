# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Foundation checks: source lock (FR-B01/PF01), editions (FR-B13/PF13), restore integrity (FR-B12/PF12)."""

import json
import pathlib
import subprocess
import sys

import pytest
from django.core.management import call_command

from plane.package_flow import editions
from plane.package_flow.models import PackageProfile, PackageRevision

REPO = pathlib.Path(__file__).resolve().parents[5]


@pytest.mark.unit
def test_pf01_fr_b01_build_commit_matches_upstream_lock():
    lock = json.loads((REPO / "docs/project-hub/upstream-lock.json").read_text())
    prd_lock = json.loads((REPO / "docs/project-hub/prd/foundation/upstream-lock.json").read_text())
    # Implementation baseline equals the analysed commit, or is reached from it only
    # through explicitly recorded upstream bumps (PF01: no silent baseline change).
    chain = prd_lock["analysisCommit"]
    for bump in lock.get("upstreamBumps", []):
        assert bump["from"] == chain and bump.get("approvedBy"), bump
        chain = bump["to"]
    assert lock["implementationCommit"] == chain
    assert lock["licensePathApproved"] is False  # L01 is not decided by code
    if not (REPO / ".git").exists():
        pytest.skip("no git checkout")
    res = subprocess.run(
        [sys.executable, str(REPO / "tools/project-hub/verify_upstream_lock.py")], capture_output=True, text=True
    )
    if "not present in this clone" in res.stdout:
        pytest.skip("shallow clone without locked commit")
    assert res.returncode == 0, res.stdout


@pytest.mark.unit
def test_pf13_fr_b13_cloud_feature_is_not_community_evidence():
    reg = {c["id"]: c for c in editions.register()}
    for enterprise in ("saml_sso", "scim_provisioning", "commercial_portfolio_features", "plane_cloud_ai_features"):
        assert reg[enterprise]["effective_status"] == "needs_verification"
    assert not editions.accept_evidence("marketing")
    assert not editions.accept_evidence("cloud_docs")
    assert editions.accept_evidence("source_file")
    # A capability claimed as native without existing source files degrades to needs_verification.
    fake = {"id": "x", "status": "native", "evidence": ["apps/api/plane/does_not_exist.py"]}
    assert editions.evaluate(fake) == "needs_verification"
    assert reg["issues_drafts_states"]["effective_status"] == "native"


@pytest.mark.unit
def test_pf12_fr_b12_integrity_snapshot_detects_loss(world, tmp_path):
    project = world.project()
    issue = world.issue(project)
    PackageProfile.objects.create(issue=issue)
    rev = PackageRevision.objects.create(issue=issue, number=1, title="t", content_hash="a" * 64)
    before, same, after = tmp_path / "b.json", tmp_path / "s.json", tmp_path / "a.json"
    call_command("package_flow_integrity_snapshot", out=str(before))
    call_command("package_flow_integrity_snapshot", out=str(same))
    script = REPO / "tools/project-hub/verify_restore.py"
    ok = subprocess.run([sys.executable, str(script), str(before), str(same)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    PackageRevision.objects.filter(pk=rev.pk).delete()
    call_command("package_flow_integrity_snapshot", out=str(after))
    bad = subprocess.run([sys.executable, str(script), str(before), str(after)], capture_output=True, text=True)
    assert bad.returncode == 1
    assert "pf_revisions" in bad.stdout
