# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project Hub external runner (PRD §13.1 "Ausführung", I06/I07).

The runner is a separate process that connects *outbound* to the Plane
server. Untrusted repository code only ever runs here, never inside the Plane
web/API/live processes. Runtime dependencies: Python standard library only.
"""

__version__ = "0.1.0"
CONTRACT_VERSION = "1.1.0"
