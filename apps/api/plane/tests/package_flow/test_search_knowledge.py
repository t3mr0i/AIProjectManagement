# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Uploads (FR-C05, FR-E04) and ACL search (FR-P06, PRD §15.2)."""

import io
import zipfile

import pytest

from plane.db.models import FileAsset, Page, ProjectPage
from plane.package_flow.models import SearchDocument, UploadRecord
from plane.package_flow.services import knowledge


def docx_bytes(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
                                        "</w:document>")
    return buf.getvalue()


def setup(world):
    alice, bob = world.member(), world.member()
    project = world.project(identifier="KNW", members=[(alice, 15), (bob, 15)])
    world.enable(project)
    return project, alice, bob


def register(world, project, client, monkeypatch, name, content, declared=""):
    asset = FileAsset.objects.create(attributes={"name": name, "type": declared}, asset=f"u/{name}",
                                     workspace=world.workspace, project=project)
    monkeypatch.setattr(knowledge, "read_asset_bytes", lambda a, limit=None: content)
    r = client.post(f"{world.base(project)}/uploads/{asset.id}/register",
                    {"declared_mime": declared, "filename": name}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.unit
class TestUploads:
    def test_fr_e04_docx_is_not_native_editable(self, world, human_client, monkeypatch):
        project, alice, _ = setup(world)
        client = human_client(alice)
        rec = register(world, project, client, monkeypatch, "spec.docx", docx_bytes("Quarterly roadmap narwhal"),
                       declared="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert rec["format_support"] in ("preview", "download")
        assert rec["format_support"] != "native_edit"
        assert rec["detected_mime"].endswith("wordprocessingml.document")
        assert rec["scan_status"] == "clean" and rec["has_extracted_text"]
        # Stored unchanged on the native asset; the record only classifies it.
        assert UploadRecord.objects.get(id=rec["id"]).asset.asset.name == "u/spec.docx"
        results = client.get(f"{world.ws_base()}/search/?q=narwhal").json()["results"]
        assert [r["type"] for r in results] == ["upload"]

        assert knowledge.format_support("text/markdown", "a.md") == "native_edit"
        assert knowledge.format_support("image/png", "a.png") == "comment"
        assert knowledge.format_support("application/pdf", "a.pdf") == "preview"
        assert knowledge.format_support("application/octet-stream", "a.bin") == "download"

    def test_mime_sniffing_and_quarantine(self, world, human_client, monkeypatch):
        project, alice, _ = setup(world)
        client = human_client(alice)
        rec = register(world, project, client, monkeypatch, "photo.png", b"MZ\x90\x00binary", declared="image/png")
        assert rec["detected_mime"] == "application/x-msdownload"
        assert rec["scan_status"] == "quarantined"
        rec = register(world, project, client, monkeypatch, "run.sh", b"#!/bin/sh\nrm -rf /", declared="text/plain")
        assert rec["scan_status"] == "quarantined"
        rec = register(world, project, client, monkeypatch, "img.png", b"\x89PNG\r\n\x1a\n....", declared="image/png")
        assert rec["scan_status"] == "clean" and rec["format_support"] == "comment"
        # Not readable yet -> pending, never indexed.
        asset = FileAsset.objects.create(attributes={"name": "later.txt"}, asset="u/later.txt",
                                         workspace=world.workspace, project=project)
        monkeypatch.setattr(knowledge, "read_asset_bytes", lambda a, limit=None: None)
        r = client.post(f"{world.base(project)}/uploads/{asset.id}/register", {}, format="json").json()
        assert r["scan_status"] == "pending"
        assert not SearchDocument.objects.filter(object_type="upload", object_id=r["id"]).exists()

    def test_scanner_hook_is_configurable(self, settings, world, human_client, monkeypatch):
        settings.PACKAGE_FLOW_UPLOAD_SCANNER = "plane.tests.package_flow.test_search_knowledge.reject_all"
        project, alice, _ = setup(world)
        rec = register(world, project, human_client(alice), monkeypatch, "a.txt", b"hello")
        assert rec["scan_status"] == "quarantined" and rec["scan_detail"] == "policy"

    def test_foreign_asset_is_404(self, world, human_client, monkeypatch):
        project, alice, _ = setup(world)
        other = world.project(identifier="OTR")
        asset = FileAsset.objects.create(attributes={"name": "x.txt"}, asset="u/x.txt", workspace=world.workspace,
                                         project=other)
        r = human_client(alice).post(f"{world.base(project)}/uploads/{asset.id}/register", {}, format="json")
        assert r.status_code == 404


def reject_all(content, meta):
    return "quarantined", "policy"


@pytest.mark.unit
class TestSearch:
    def test_same_query_different_rights_no_hidden_counts(self, world, human_client):
        project, alice, bob = setup(world)
        secret_project = world.project(identifier="SEC", members=[(alice, 15)])
        world.issue(project, name="Pelican dashboard")
        world.issue(secret_project, name="Pelican acquisition secret")
        page = Page.objects.create(workspace=world.workspace, name="Pelican notes", owned_by=alice,
                                   description_html="<p>pelican</p>", description_stripped="pelican")
        ProjectPage.objects.create(project=project, page=page, workspace=world.workspace)
        a = human_client(alice).get(f"{world.ws_base()}/search/?q=pelican").json()
        b = human_client(bob).get(f"{world.ws_base()}/search/?q=pelican").json()
        assert set(b.keys()) == {"results"}
        a_titles = {r["title"] for r in a["results"]}
        b_titles = {r["title"] for r in b["results"]}
        assert "Pelican acquisition secret" in a_titles
        assert "Pelican acquisition secret" not in b_titles
        assert {"Pelican dashboard", "Pelican notes"} <= b_titles
        for r in b["results"]:
            assert r["project_id"] != str(secret_project.id)
            assert {"type", "id", "title", "snippet", "project_id", "source", "updated_at"} <= set(r)

    def test_full_text_ranking_keeps_acl(self, world, human_client):
        project, alice, bob = setup(world)
        secret_project = world.project(identifier="SE2", members=[(alice, 15)])
        world.issue(project, name="Misc", description_html="<p>x</p>").__class__.objects.filter(
            name="Misc").update(description_stripped="something about invoices somewhere")
        best = world.issue(project, name="Invoice export")
        world.issue(secret_project, name="Invoice export secret")
        # Word-based match (stemming-free "simple" config) plus substring fallback.
        results = human_client(bob).get(f"{world.ws_base()}/search/?q=invoice export").json()["results"]
        assert results and results[0]["id"] == str(best.id)
        assert results[0]["rank"] > 0
        assert all("secret" not in r["title"] for r in results)
        partial = human_client(bob).get(f"{world.ws_base()}/search/?q=nvoic").json()["results"]
        assert str(best.id) in [r["id"] for r in partial]
