# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Domain errors with stable machine codes and HTTP status (PRD §13.4: 401/403/409/422/429)."""


class DomainError(Exception):
    status_code = 422
    code = "DOMAIN_ERROR"

    def __init__(self, message="", code=None, status_code=None, detail=None):
        super().__init__(message or self.code)
        self.message = message or self.code
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.detail = detail or {}

    def as_dict(self):
        body = {"error": self.message, "code": self.code}
        if self.detail:
            body["detail"] = self.detail
        return body


class NotFound(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class PermissionDenied(DomainError):
    status_code = 403
    code = "PERMISSION_DENIED"


class HumanPrincipalRequired(PermissionDenied):
    code = "HUMAN_PRINCIPAL_REQUIRED"


class Conflict(DomainError):
    status_code = 409
    code = "CONFLICT"


class ValidationFailed(DomainError):
    status_code = 422
    code = "VALIDATION_FAILED"


class ExtensionDisabled(DomainError):
    status_code = 403
    code = "EXTENSION_DISABLED"
