/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Vercel Routing Middleware.
 *
 * The web and admin apps are served as static bundles from Vercel, while the
 * Plane backend (Django API) runs elsewhere. Proxying /api and /auth through the
 * Vercel domain keeps the frontend and API same-origin, so the backend's
 * session and CSRF cookies work without cross-site cookie configuration.
 *
 * Set PLANE_API_URL (e.g. https://api.example.com) in the Vercel project.
 */

export const config = {
  matcher: ["/api/:path*", "/auth/:path*"],
};

export default function middleware(request: Request): Response {
  const apiUrl = process.env.PLANE_API_URL?.trim().replace(/\/+$/, "");

  if (!apiUrl) {
    return Response.json(
      { error: "Backend not configured. Set PLANE_API_URL in the Vercel project settings." },
      { status: 503 }
    );
  }

  const { pathname, search } = new URL(request.url);
  // Equivalent of `rewrite()` from @vercel/functions: proxy to an external origin.
  return new Response(null, {
    headers: { "x-middleware-rewrite": `${apiUrl}${pathname}${search}` },
  });
}
