# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os
import uuid
from datetime import timedelta

# Third party imports
import boto3
from botocore.exceptions import ClientError
from urllib.parse import quote
from google.api_core.exceptions import GoogleAPIError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage as gcs

# Django imports
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

# Module imports
from plane.utils.exception_logger import log_exception
from storages.backends.s3boto3 import S3Boto3Storage


def is_gcs_backend():
    """True when uploads go to Google Cloud Storage / Firebase Storage instead of S3/MinIO"""
    return os.environ.get("STORAGE_BACKEND", "s3").lower() in ("gcs", "firebase")


def get_storage(request=None):
    """Return the storage backend configured through STORAGE_BACKEND"""
    if is_gcs_backend():
        return GCSStorage()
    return S3Storage(request=request)


def _content_disposition(disposition, filename=None):
    """Build a Content-Disposition header value (same format as S3Storage)"""
    if filename is None:
        filename = uuid.uuid4().hex
    if filename:
        return f"{disposition}; filename*=UTF-8''{quote(filename)}"
    return disposition


class S3Storage(S3Boto3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        return name

    """S3 storage class to generate presigned URLs for S3 objects"""

    def __init__(self, request=None):
        # Get the AWS credentials and bucket name from the environment
        self.aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        # Use the AWS_SECRET_ACCESS_KEY environment variable for the secret key
        self.aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        # Use the AWS_S3_BUCKET_NAME environment variable for the bucket name
        self.aws_storage_bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
        # Use the AWS_REGION environment variable for the region
        self.aws_region = os.environ.get("AWS_REGION")
        # Use the AWS_S3_ENDPOINT_URL environment variable for the endpoint URL
        self.aws_s3_endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("MINIO_ENDPOINT_URL")
        # Use the SIGNED_URL_EXPIRATION environment variable for the expiration time (default: 3600 seconds)
        self.signed_url_expiration = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))

        if os.environ.get("USE_MINIO") == "1":
            # Determine protocol based on environment variable
            if os.environ.get("MINIO_ENDPOINT_SSL") == "1":
                endpoint_protocol = "https"
            else:
                endpoint_protocol = request.scheme if request else "http"
            # Create an S3 client for MinIO
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
                endpoint_url=(f"{endpoint_protocol}://{request.get_host()}" if request else self.aws_s3_endpoint_url),
                config=boto3.session.Config(signature_version="s3v4"),
            )
        else:
            # Create an S3 client
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
                endpoint_url=self.aws_s3_endpoint_url,
                config=boto3.session.Config(signature_version="s3v4"),
            )

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        """Generate a presigned URL to upload an S3 object"""
        if expiration is None:
            expiration = self.signed_url_expiration
        fields = {"Content-Type": file_type}

        conditions = [
            {"bucket": self.aws_storage_bucket_name},
            ["content-length-range", 1, file_size],
            {"Content-Type": file_type},
        ]

        # Add condition for the object name (key)
        if object_name.startswith("${filename}"):
            conditions.append(["starts-with", "$key", object_name[: -len("${filename}")]])
        else:
            fields["key"] = object_name
            conditions.append({"key": object_name})

        # Generate the presigned POST URL
        try:
            # Generate a presigned URL for the S3 object
            response = self.s3_client.generate_presigned_post(
                Bucket=self.aws_storage_bucket_name,
                Key=object_name,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expiration,
            )
        # Handle errors
        except ClientError as e:
            print(f"Error generating presigned POST URL: {e}")
            return None

        return response

    def _get_content_disposition(self, disposition, filename=None):
        """Helper method to generate Content-Disposition header value"""
        return _content_disposition(disposition, filename)

    def generate_presigned_url(
        self,
        object_name,
        expiration=None,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        """Generate a presigned URL to share an S3 object"""
        if expiration is None:
            expiration = self.signed_url_expiration
        content_disposition = self._get_content_disposition(disposition, filename)
        try:
            response = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.aws_storage_bucket_name,
                    "Key": str(object_name),
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=expiration,
                HttpMethod=http_method,
            )
        except ClientError as e:
            log_exception(e)
            return None

        # The response contains the presigned URL
        return response

    def get_object_metadata(self, object_name):
        """Get the metadata for an S3 object"""
        try:
            response = self.s3_client.head_object(Bucket=self.aws_storage_bucket_name, Key=object_name)
        except ClientError as e:
            log_exception(e)
            return None

        return {
            "ContentType": response.get("ContentType"),
            "ContentLength": response.get("ContentLength"),
            "LastModified": (response.get("LastModified").isoformat() if response.get("LastModified") else None),
            "ETag": response.get("ETag"),
            "Metadata": response.get("Metadata", {}),
        }

    def copy_object(self, object_name, new_object_name):
        """Copy an S3 object to a new location"""
        try:
            response = self.s3_client.copy_object(
                Bucket=self.aws_storage_bucket_name,
                CopySource={"Bucket": self.aws_storage_bucket_name, "Key": object_name},
                Key=new_object_name,
            )
        except ClientError as e:
            log_exception(e)
            return None

        return response

    def upload_file(
        self,
        file_obj,
        object_name: str,
        content_type: str = None,
        extra_args: dict = {},
    ) -> bool:
        """Upload a file directly to S3"""
        try:
            if content_type:
                extra_args["ContentType"] = content_type

            self.s3_client.upload_fileobj(
                file_obj,
                self.aws_storage_bucket_name,
                object_name,
                ExtraArgs=extra_args,
            )
            return True
        except ClientError as e:
            log_exception(e)
            return False

    def delete_files(self, object_names):
        """Delete an S3 object"""
        try:
            self.s3_client.delete_objects(
                Bucket=self.aws_storage_bucket_name,
                Delete={"Objects": [{"Key": object_name} for object_name in object_names]},
            )
            return True
        except ClientError as e:
            log_exception(e)
            return False


@deconstructible
class GCSStorage(Storage):
    """Google Cloud Storage backend, used for Firebase Storage buckets.

    Exposes the same helper methods as S3Storage so views and background tasks
    work unchanged. Credentials come from Application Default Credentials
    (GOOGLE_APPLICATION_CREDENTIALS pointing at a service account key, or the
    attached service account on Google Cloud).
    """

    def __init__(self):
        # Firebase buckets are named "<project-id>.firebasestorage.app" (or ".appspot.com")
        self.bucket_name = os.environ.get("GCS_BUCKET_NAME") or os.environ.get("AWS_S3_BUCKET_NAME")
        self.signed_url_expiration = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))
        self.client = gcs.Client(project=os.environ.get("GCS_PROJECT_ID") or None)
        self.bucket = self.client.bucket(self.bucket_name)

    def _signing_kwargs(self):
        """Extra arguments needed to sign URLs with credentials that hold no private key.

        A service account key file can sign locally. Credentials from the metadata
        server (Cloud Run, GCE) cannot, so the IAM signBlob API is used through the
        service account email and an access token instead.
        """
        credentials = self.client._credentials
        if hasattr(credentials, "sign_bytes") and hasattr(credentials, "signer_email"):
            return {}
        service_account_email = getattr(credentials, "service_account_email", None)
        if not service_account_email:
            raise ValueError("Signing GCS URLs requires service account credentials")
        if not credentials.valid:
            credentials.refresh(GoogleAuthRequest())
        return {
            "service_account_email": service_account_email,
            "access_token": credentials.token,
        }

    def url(self, name, parameters=None, expire=None, http_method=None):
        return name

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        """Generate a signed POST policy to upload an object; returns {"url", "fields"} like S3"""
        if expiration is None:
            expiration = self.signed_url_expiration
        try:
            return self.client.generate_signed_post_policy_v4(
                self.bucket_name,
                object_name,
                expiration=timedelta(seconds=expiration),
                conditions=[
                    ["content-length-range", 1, file_size],
                    {"Content-Type": file_type},
                ],
                fields={"Content-Type": file_type},
                scheme="https",
                **self._signing_kwargs(),
            )
        except (GoogleAPIError, ValueError) as e:
            log_exception(e)
            return None

    def generate_presigned_url(
        self,
        object_name,
        expiration=None,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        """Generate a signed URL to share an object"""
        if expiration is None:
            expiration = self.signed_url_expiration
        try:
            return self.bucket.blob(str(object_name)).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expiration),
                method=http_method,
                response_disposition=_content_disposition(disposition, filename),
                **self._signing_kwargs(),
            )
        except (GoogleAPIError, ValueError) as e:
            log_exception(e)
            return None

    def get_object_metadata(self, object_name):
        """Get the metadata for an object, in the same shape S3Storage returns"""
        try:
            blob = self.bucket.get_blob(str(object_name))
        except GoogleAPIError as e:
            log_exception(e)
            return None
        if blob is None:
            return None

        return {
            "ContentType": blob.content_type,
            "ContentLength": blob.size,
            "LastModified": blob.updated.isoformat() if blob.updated else None,
            "ETag": blob.etag,
            "Metadata": blob.metadata or {},
        }

    def copy_object(self, object_name, new_object_name):
        """Copy an object to a new location in the same bucket"""
        try:
            return self.bucket.copy_blob(self.bucket.blob(str(object_name)), self.bucket, str(new_object_name))
        except GoogleAPIError as e:
            log_exception(e)
            return None

    def upload_file(self, file_obj, object_name: str, content_type: str = None, extra_args: dict = None) -> bool:
        """Upload a file directly to the bucket"""
        try:
            self.bucket.blob(object_name).upload_from_file(file_obj, content_type=content_type, rewind=True)
            return True
        except GoogleAPIError as e:
            log_exception(e)
            return False

    def delete_files(self, object_names):
        """Delete objects; missing objects are ignored"""
        try:
            self.bucket.delete_blobs([self.bucket.blob(name) for name in object_names], on_error=lambda blob: None)
            return True
        except GoogleAPIError as e:
            log_exception(e)
            return False

    # Django Storage API (used by FileField, e.g. asset.delete())
    def _open(self, name, mode="rb"):
        return ContentFile(self.bucket.blob(name).download_as_bytes(), name=name)

    def _save(self, name, content):
        content.seek(0)
        self.bucket.blob(name).upload_from_file(content, content_type=getattr(content, "content_type", None))
        return name

    def delete(self, name):
        self.delete_files([name])

    def exists(self, name):
        return self.bucket.blob(name).exists()

    def size(self, name):
        blob = self.bucket.get_blob(name)
        return blob.size if blob else 0
