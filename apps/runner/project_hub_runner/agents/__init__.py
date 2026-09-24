# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Agent adapters. Each receives only the manifest-derived policy gate (AC27)."""

from .base import AgentAdapter, AgentResult, TaskSpec

__all__ = ["AgentAdapter", "AgentResult", "TaskSpec"]
