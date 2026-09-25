# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from urllib.parse import urlparse

# Django imports
from django.conf import settings
from django.core.management import BaseCommand

# Third party imports
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError

# Module imports
from plane.settings.storage import GCSStorage


def get_cors_origins():
    """Origins of the web apps that upload straight to the bucket"""
    urls = [
        settings.WEB_URL,
        settings.APP_BASE_URL,
        settings.ADMIN_BASE_URL,
        settings.SPACE_BASE_URL,
        *getattr(settings, "CORS_ALLOWED_ORIGINS", []),
    ]
    origins = set()
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(origins)


class Command(BaseCommand):
    help = "Check the Google Cloud Storage / Firebase Storage bucket and set the CORS rules browser uploads need"

    def handle(self, *args, **options):
        try:
            storage = GCSStorage()
            bucket = storage.client.get_bucket(storage.bucket_name)
        except (GoogleAPIError, GoogleAuthError) as e:
            self.stdout.write(self.style.ERROR(f"Cannot access the storage bucket: {e}"))
            return

        origins = get_cors_origins()
        if not origins:
            self.stdout.write(self.style.WARNING("WEB_URL is not set, skipping CORS configuration."))
            return

        bucket.cors = [
            {
                "origin": origins,
                "method": ["GET", "HEAD", "POST", "PUT"],
                "responseHeader": ["Content-Type", "Content-Disposition", "ETag"],
                "maxAgeSeconds": 3600,
            }
        ]
        try:
            bucket.patch()
        except GoogleAPIError as e:
            self.stdout.write(self.style.ERROR(f"Failed to set CORS on bucket '{storage.bucket_name}': {e}"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"Bucket '{storage.bucket_name}' ready, CORS origins: {', '.join(origins)}")
        )
