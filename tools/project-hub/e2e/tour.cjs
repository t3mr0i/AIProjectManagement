// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
// Screenshot tour of the Project Hub screens against running API (:8000) and web (:3000).
// Usage: E2E_SEED_OUT=<seed.json> TOUR_OUT=<dir> node tools/project-hub/e2e/tour.cjs
const { chromium } = require("playwright");
const seed = require(process.env.E2E_SEED_OUT || "/tmp/project-hub-e2e/seed.json");
const API = "http://localhost:8000", WEB = "http://localhost:3000";
const OUT = process.env.TOUR_OUT || "docs/project-hub/screenshots/tour";
require("fs").mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const csrf = await context.request.get(`${API}/auth/get-csrf-token/`);
  const token = (await csrf.json()).csrf_token;
  await context.request.post(`${API}/auth/sign-in/`, {
    form: { email: seed.email, password: seed.password, csrfmiddlewaretoken: token },
    headers: { "X-CSRFToken": token, Referer: WEB }, maxRedirects: 0,
  });
  const me = await context.request.get(`${API}/api/users/me/`);
  console.log("me", me.status());
  const page = await context.newPage();
  const ws = seed.workspace_slug, pid = seed.project_id;
  const shots = [
    ["01-workitem", `${WEB}/${ws}/browse/${seed.project_identifier}-${seed.issue_sequence}/`],
    ["02-overview", `${WEB}/${ws}/hub`],
    ["03-packages", `${WEB}/${ws}/projects/${pid}/hub/packages`],
    ["04-activity", `${WEB}/${ws}/projects/${pid}/hub/activity`],
    ["05-roadmap", `${WEB}/${ws}/hub/roadmap`],
    ["06-settings", `${WEB}/${ws}/settings/project-hub`],
  ];
  for (const [name, url] of shots) {
    await page.goto(url, { waitUntil: "networkidle", timeout: 120000 }).catch((e) => console.log(name, e.message));
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${OUT}/${name}.png` });
    console.log(name, page.url());
  }
  await browser.close();
})();
