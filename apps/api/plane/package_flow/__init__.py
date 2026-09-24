# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project Hub package-flow extension.

Additive, feature-flagged extension of native Plane Issues. A work package is a
native ``db.Issue`` plus an optional 0..1 ``PackageProfile``; there is no
independent package identity (PRD 0.2, FR-B02).
"""
