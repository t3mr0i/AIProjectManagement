/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* eslint-disable no-console */
/**
 * Project Hub browser test against a real local stack (API :8000 + web dev server :3000).
 * apps/web has no Playwright setup, so this is a plain script on the `playwright` library.
 *
 * Normally started via tools/project-hub/e2e/run.sh (seeds, starts servers, runs this).
 * Direct run (servers already up, seed written by seed.py):
 *   NODE_PATH=$(npm root -g) PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node tools/project-hub/e2e/project-hub.e2e.cjs
 *
 * Env: E2E_SEED_OUT (seed json, default /tmp/project-hub-e2e-seed.json), E2E_API (http://localhost:8000),
 * E2E_WEB (http://localhost:3000), E2E_SHOTS (docs/project-hub/screenshots), E2E_HEADED=1.
 * Exit code 1 on a failed step or an uncaught page error.
 */
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "../../..");
const SEED = JSON.parse(fs.readFileSync(process.env.E2E_SEED_OUT || "/tmp/project-hub-e2e-seed.json", "utf8"));
const API = process.env.E2E_API || "http://localhost:8000";
const WEB = process.env.E2E_WEB || "http://localhost:3000";
const SHOTS = path.resolve(ROOT, process.env.E2E_SHOTS || "docs/project-hub/screenshots");
const TIMEOUT = 30_000;

fs.mkdirSync(SHOTS, { recursive: true });

// Known native Plane dev-mode noise (not Project Hub): SSR hydration mismatch of the root loading
// screen and the nested drag-handle button in the native sidebar project list.
const NATIVE_NOISE = [/hydration/i, /cannot (be a descendant|contain a nested)/i];
const isNativeNoise = (text) => NATIVE_NOISE.some((re) => re.test(text));
const nativeNoise = [];
const pageErrors = [];
const consoleErrors = [];
const failedRequests = [];

async function shot(page, name) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(400); // let tab indicators / toasts settle
  const file = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  screenshot ${path.relative(ROOT, file)}`);
}

let currentPage = null;

async function step(name, fn) {
  const started = Date.now();
  process.stdout.write(`- ${name} … `);
  try {
    await fn();
    console.log(`ok (${Date.now() - started} ms)`);
  } catch (err) {
    console.log("FAILED");
    if (currentPage)
      await shot(currentPage, `failed-${name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`).catch(() => undefined);
    throw new Error(`${name}: ${err.message}`, { cause: err });
  }
}

async function login(context) {
  // Plane session login through the API (same cookie the web app uses).
  const csrf = await context.request.get(`${API}/auth/get-csrf-token/`);
  const { csrf_token: token } = await csrf.json();
  const res = await context.request.post(`${API}/auth/sign-in/`, {
    form: { csrfmiddlewaretoken: token, email: SEED.email, password: SEED.password, next_path: "" },
    headers: { Referer: `${WEB}/`, Origin: WEB },
    maxRedirects: 0,
  });
  const me = await context.request.get(`${API}/api/users/me/`);
  if (me.status() !== 200) throw new Error(`login failed (sign-in ${res.status()}, me ${me.status()})`);
}

async function main() {
  const browser = await chromium.launch({ headless: !process.env.E2E_HEADED });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1800 }, locale: "en-US" });
  context.setDefaultTimeout(TIMEOUT);
  const page = await context.newPage();
  currentPage = page;
  page.on("pageerror", (err) =>
    (isNativeNoise(err.message) ? nativeNoise : pageErrors).push(`${page.url()}: ${err.message.split("\n")[0]}`)
  );
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    (isNativeNoise(text) ? nativeNoise : consoleErrors).push(`${page.url()}: ${text.split("\n")[0]}`);
  });
  page.on("response", (res) => {
    if (res.url().includes("/package-flow/") && res.status() >= 500)
      failedRequests.push(`${res.status()} ${res.url()}`);
  });

  const ws = SEED.workspace_slug;
  const pid = SEED.project_id;
  const issueUrl = `${WEB}/${ws}/browse/${SEED.project_identifier}-${SEED.issue_sequence}/`;

  await step("log in through the API session", () => login(context));

  await step("open the work item and activate it as a work package", async () => {
    await page.goto(issueUrl);
    const activate = page.getByRole("button", { name: "Activate as work package" });
    await activate.waitFor();
    await shot(page, "01-issue-normal-work-item");
    await activate.click();
    await page.getByRole("tablist", { name: "Work package sections" }).waitFor();
    await shot(page, "02-work-package-activated");
  });

  await step("fill the brief and save the draft", async () => {
    await page.getByLabel("Goal / why").fill("Finance needs invoice data in their spreadsheet tool.");
    await page.getByLabel("Desired outcome").fill("Users can download all invoices of a period as CSV.");
    await page.getByLabel("Scope").fill("Invoice list export button\nCSV endpoint");
    await page.getByRole("button", { name: "Add criterion" }).click();
    await page.getByLabel("Criterion 1", { exact: true }).fill("The CSV contains one row per invoice of the period.");
    await page.getByRole("button", { name: "Save draft" }).click();
    await page.getByText("Draft saved").first().waitFor();
    await page.getByText("Ready for approval").first().waitFor();
    await shot(page, "03-brief-ready");
  });

  await step("create a revision", async () => {
    await page.getByRole("button", { name: "Create revision" }).click();
    await page
      .getByText(/Revision 1 created/)
      .first()
      .waitFor();
    await page.getByText("Revision 1").first().waitFor();
    await shot(page, "04-revision-created");
  });

  await step("changes tab with diagrams", async () => {
    await page.getByRole("tab", { name: "Changes" }).click();
    await page.getByRole("heading", { name: "Diagrams" }).waitFor();
    await shot(page, "05-changes-tab");
  });

  await step("diagram editor: semantic change → pending interpretation", async () => {
    const diagrams = page.getByRole("region", { name: "Diagrams" });
    await diagrams.getByRole("button", { name: "New diagram" }).click();
    const dialog = page.getByRole("dialog", { name: "New diagram" });
    await dialog.getByLabel("Name").fill("Invoice export flow");
    await dialog.getByRole("button", { name: "New diagram" }).click();
    await dialog.waitFor({ state: "detached" });
    await diagrams.getByRole("button", { name: "Add node" }).click();
    await diagrams.getByRole("button", { name: "Add node" }).click();
    const labels = diagrams.getByLabel("Label", { exact: true });
    await labels.nth(0).fill("Invoice list");
    await labels.nth(1).fill("CSV endpoint");
    // An edge without type/label is ambiguous → the interpretation asks a question about it.
    await diagrams.getByRole("button", { name: "Add edge" }).click();
    await diagrams.getByRole("button", { name: "Save", exact: true }).click();
    await diagrams.getByText(/the meaning changed/).waitFor();
    await diagrams.getByText("Pending interpretation").first().waitFor();
    await shot(page, "06-diagram-semantic-change");
  });

  await step("diagram editor: keyboard move is layout-only", async () => {
    const diagrams = page.getByRole("region", { name: "Diagrams" });
    const node = diagrams.getByRole("button", { name: /^CSV endpoint \(/ });
    await node.focus();
    // oxlint-disable-next-line no-await-in-loop -- key presses must be sequential
    for (let i = 0; i < 5; i += 1) await page.keyboard.press("Shift+ArrowDown");
    await diagrams.getByRole("button", { name: "Save", exact: true }).click();
    await diagrams.getByText(/layout only/).waitFor();
    await shot(page, "07-diagram-layout-only");
  });

  await step("project activity", async () => {
    await page.goto(`${WEB}/${ws}/projects/${pid}/hub/activity`);
    await page.getByRole("heading", { level: 1 }).first().waitFor();
    await page.waitForLoadState("networkidle");
    await shot(page, "08-project-activity");
  });

  await step("project work packages", async () => {
    await page.goto(`${WEB}/${ws}/projects/${pid}/hub/packages`);
    await page.getByText("Export CSV for invoices").first().waitFor();
    await shot(page, "09-project-work-packages");
  });

  await step("project knowledge: register an attachment, quarantine is marked", async () => {
    await page.goto(`${WEB}/${ws}/projects/${pid}/hub/knowledge`);
    await page.getByRole("heading", { name: "Diagrams" }).waitFor();
    await page.getByText("Quarantined — do not open or share. Content is blocked.").first().waitFor();
    await page.getByRole("button", { name: "Register attachment" }).click();
    const dialog = page.getByRole("dialog", { name: "Register attachment" });
    await dialog
      .getByRole("radio", { name: /requirements-/ })
      .first()
      .check();
    await shot(page, "10-knowledge-register-dialog");
    await dialog.getByRole("button", { name: "Register", exact: true }).click();
    await dialog.waitFor({ state: "detached" });
    await page
      .getByRole("status")
      .getByText(/requirements-.*registered/)
      .waitFor();
    await shot(page, "11-project-knowledge");
  });

  await step("workspace roadmap", async () => {
    await page.goto(`${WEB}/${ws}/hub/roadmap`);
    await page.getByRole("heading", { level: 1 }).first().waitFor();
    await page.waitForLoadState("networkidle");
    await shot(page, "12-workspace-roadmap");
  });

  await step("workspace settings → Project Hub", async () => {
    await page.goto(`${WEB}/${ws}/settings/project-hub`);
    await page.getByRole("heading", { name: "Project Hub", exact: true }).first().waitFor();
    await page.waitForLoadState("networkidle");
    await shot(page, "13-settings-project-hub");
  });

  await browser.close();
}

main()
  .then(() => {
    if (nativeNoise.length) console.log(`ignored native dev warnings: ${nativeNoise.length}`);
    if (consoleErrors.length) console.log(`console errors (${consoleErrors.length}):\n  ${consoleErrors.join("\n  ")}`);
    if (failedRequests.length) console.log(`5xx responses:\n  ${failedRequests.join("\n  ")}`);
    if (pageErrors.length || failedRequests.length) {
      console.error(`uncaught page errors:\n  ${pageErrors.join("\n  ")}`);
      process.exit(1);
    }
    console.log("project hub e2e: passed");
    return undefined;
  })
  .catch((err) => {
    console.error(err.message);
    if (pageErrors.length) console.error(`page errors:\n  ${pageErrors.join("\n  ")}`);
    if (consoleErrors.length) console.error(`console errors:\n  ${consoleErrors.slice(0, 20).join("\n  ")}`);
    process.exit(1);
  });
