# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI core routes. Mounted under ``api/``."""

from ..views import ai as v
from .collaboration import P, W, both

urlpatterns = [
    *both(W + "ai/status", v.AIStatusEndpoint.as_view(), "pf-ai-status"),
    *both(W + "ai/ask", v.AIAskEndpoint.as_view(), "pf-ai-ask"),
    *both(W + "ai/assist", v.AIAssistEndpoint.as_view(), "pf-ai-assist"),
    *both(W + "ai/assist/stream", v.AIAssistStreamEndpoint.as_view(), "pf-ai-assist-stream"),
    *both(W + "ai/usage", v.AIUsageEndpoint.as_view(), "pf-ai-usage"),
    *both(W + "ai/reindex", v.AIReindexEndpoint.as_view(), "pf-ai-reindex"),
    *both(P + "ai/report", v.AIProjectReportEndpoint.as_view(), "pf-ai-project-report"),
]
