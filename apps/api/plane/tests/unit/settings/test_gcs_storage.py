# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from google.api_core.exceptions import NotFound

from plane.settings.storage import GCSStorage, S3Storage, get_storage, is_gcs_backend

GCS_ENV = {
    "STORAGE_BACKEND": "gcs",
    "GCS_BUCKET_NAME": "demo.firebasestorage.app",
    "GCS_PROJECT_ID": "demo",
}


def make_storage(credentials=None):
    """Build a GCSStorage with a mocked google-cloud-storage client"""
    with patch("plane.settings.storage.gcs") as mock_gcs:
        client = MagicMock()
        client._credentials = credentials or Mock(spec=["sign_bytes", "signer_email"])
        mock_gcs.Client.return_value = client
        storage = GCSStorage()
    return storage, client


@pytest.mark.unit
class TestBackendSelection:
    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_to_s3(self):
        assert is_gcs_backend() is False
        with patch("plane.settings.storage.boto3"):
            assert isinstance(get_storage(), S3Storage)

    @pytest.mark.parametrize("value", ["gcs", "GCS", "firebase"])
    def test_gcs_values(self, value):
        with patch.dict(os.environ, {**GCS_ENV, "STORAGE_BACKEND": value}, clear=True):
            assert is_gcs_backend() is True
            with patch("plane.settings.storage.gcs"):
                assert isinstance(get_storage(), GCSStorage)


@pytest.mark.unit
@patch.dict(os.environ, GCS_ENV, clear=True)
class TestGCSStorage:
    def test_bucket_and_project_from_env(self):
        with patch("plane.settings.storage.gcs") as mock_gcs:
            GCSStorage()
        mock_gcs.Client.assert_called_once_with(project="demo")
        mock_gcs.Client.return_value.bucket.assert_called_once_with("demo.firebasestorage.app")

    def test_bucket_falls_back_to_aws_bucket_name(self):
        with patch.dict(os.environ, {"GCS_BUCKET_NAME": "", "AWS_S3_BUCKET_NAME": "uploads"}):
            storage, _ = make_storage()
        assert storage.bucket_name == "uploads"

    def test_presigned_post_has_s3_shape_and_limits(self):
        storage, client = make_storage()
        client.generate_signed_post_policy_v4.return_value = {"url": "https://storage.googleapis.com/b/", "fields": {}}

        result = storage.generate_presigned_post("ws/abc.png", "image/png", 1024)

        assert result == {"url": "https://storage.googleapis.com/b/", "fields": {}}
        args, kwargs = client.generate_signed_post_policy_v4.call_args
        assert args == ("demo.firebasestorage.app", "ws/abc.png")
        assert kwargs["expiration"] == timedelta(seconds=3600)
        assert ["content-length-range", 1, 1024] in kwargs["conditions"]
        assert {"Content-Type": "image/png"} in kwargs["conditions"]
        assert kwargs["fields"] == {"Content-Type": "image/png"}
        assert "access_token" not in kwargs

    def test_presigned_post_uses_iam_signing_without_private_key(self):
        credentials = Mock(spec=["service_account_email", "valid", "token", "refresh"])
        credentials.service_account_email = "plane@demo.iam.gserviceaccount.com"
        credentials.valid = True
        credentials.token = "token-123"
        storage, client = make_storage(credentials)

        storage.generate_presigned_post("key", "image/png", 10)

        kwargs = client.generate_signed_post_policy_v4.call_args.kwargs
        assert kwargs["service_account_email"] == "plane@demo.iam.gserviceaccount.com"
        assert kwargs["access_token"] == "token-123"

    def test_presigned_post_returns_none_for_user_credentials(self):
        storage, client = make_storage(Mock(spec=["valid", "token"]))
        assert storage.generate_presigned_post("key", "image/png", 10) is None
        client.generate_signed_post_policy_v4.assert_not_called()

    def test_presigned_url_sets_disposition_and_expiration(self):
        storage, client = make_storage()
        blob = client.bucket.return_value.blob.return_value
        blob.generate_signed_url.return_value = "https://signed"

        url = storage.generate_presigned_url("ws/file.pdf", expiration=60, disposition="attachment", filename="a b.pdf")

        assert url == "https://signed"
        kwargs = blob.generate_signed_url.call_args.kwargs
        assert kwargs["version"] == "v4"
        assert kwargs["expiration"] == timedelta(seconds=60)
        assert kwargs["method"] == "GET"
        assert kwargs["response_disposition"] == "attachment; filename*=UTF-8''a%20b.pdf"

    def test_metadata_has_s3_shape(self):
        storage, client = make_storage()
        blob = Mock(
            content_type="image/png",
            size=42,
            updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
            etag="etag",
            metadata=None,
        )
        client.bucket.return_value.get_blob.return_value = blob

        assert storage.get_object_metadata("key") == {
            "ContentType": "image/png",
            "ContentLength": 42,
            "LastModified": "2026-01-01T00:00:00+00:00",
            "ETag": "etag",
            "Metadata": {},
        }

    def test_metadata_missing_object(self):
        storage, client = make_storage()
        client.bucket.return_value.get_blob.return_value = None
        assert storage.get_object_metadata("missing") is None

    def test_copy_object(self):
        storage, client = make_storage()
        bucket = client.bucket.return_value

        storage.copy_object("src", "dst")

        bucket.copy_blob.assert_called_once_with(bucket.blob.return_value, bucket, "dst")

    def test_copy_object_error_returns_none(self):
        storage, client = make_storage()
        client.bucket.return_value.copy_blob.side_effect = NotFound("gone")
        assert storage.copy_object("src", "dst") is None

    def test_upload_file(self):
        storage, client = make_storage()
        file_obj = Mock()

        assert storage.upload_file(file_obj, "avatar.png", content_type="image/png") is True

        client.bucket.return_value.blob.return_value.upload_from_file.assert_called_once_with(
            file_obj, content_type="image/png", rewind=True
        )

    def test_delete_files(self):
        storage, client = make_storage()
        assert storage.delete_files(["a", "b"]) is True
        client.bucket.return_value.delete_blobs.assert_called_once()

    def test_url_returns_key(self):
        storage, _ = make_storage()
        assert storage.url("ws/key.png") == "ws/key.png"
