/**
 * Critical-path E2E for Trudnik (J133).
 *
 * Covers: registration → employer creates a job → worker applies →
 * employer accepts → both sides exchange a chat message.
 *
 * Run via scripts/e2e/run_critical_flows.sh (starts runserver + seeds DB).
 * Requires Playwright chromium installed locally (`npx playwright install chromium`).
 */
import { chromium } from "playwright";

const BASE = process.env.E2E_BASE_URL || "http://127.0.0.1:8801";
const PASSWORD = "Aa1!aaaa"; // pragma: allowlist secret
const EMPLOYER = "e2e-employer@example.com";
const WORKER = "e2e-worker@example.com";
const JOB_TITLE = "E2E Уборка";
const MESSAGE = "E2E сообщение " + Date.now();

let passed = 0;
const failures = [];

function ok(name) {
  passed += 1;
  console.log("  ✓ " + name);
}

function fail(name, error) {
  failures.push({ name, error });
  console.error("  ✗ " + name + ": " + (error && error.message ? error.message : error));
}

async function check(name, fn) {
  try {
    await fn();
    ok(name);
  } catch (error) {
    fail(name, error);
    throw error;
  }
}

async function newPage(browser, viewport = { width: 1280, height: 1000 }) {
  const context = await browser.newContext({
    locale: "ru-RU",
    viewport,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  return { context, page };
}

async function login(browser, email, viewport) {
  const { context, page } = await newPage(browser, viewport);
  await page.goto(BASE + "/login", { waitUntil: "domcontentloaded" });
  await page.fill("#email", email);
  await page.fill("#password", PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 20000 });
  await page.waitForFunction(() => document.body.dataset.userId, null, { timeout: 15000 });
  return { context, page };
}

function futureLocalDateTime(days) {
  const date = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
    "T" + pad(date.getHours()) + ":" + pad(date.getMinutes())
  );
}

async function register(browser) {
  const { context, page } = await newPage(browser);
  const email = "e2e-reg-" + Date.now() + "@example.com";
  await page.goto(BASE + "/register", { waitUntil: "domcontentloaded" });
  await page.fill("#full_name", "E2E Регистрация");
  await page.fill("#email", email);
  await page.fill("#password", PASSWORD);
  await page.click("#register-next");
  await page.locator('[data-register-step="2"]').waitFor({ state: "visible" });
  await page.fill("#city", "Москва");
  await page.click("#register-next");
  await page.locator('[data-register-step="3"]').waitFor({ state: "visible" });
  await page.locator('input[name="consent"]').check({ force: true });
  await page.locator('#register-submit-wrap button[type="submit"]').click();
  await page.waitForURL(/verify-email/, { timeout: 25000 });
  const body = await page.locator("body").innerText();
  if (!body.includes("Аккаунт создан")) {
    throw new Error("registration confirmation is missing");
  }
  await context.close();
  return email;
}

async function createJob(browser) {
  const { context, page } = await login(browser, EMPLOYER);
  await page.goto(BASE + "/jobs/new", { waitUntil: "domcontentloaded" });
  await page.fill("#id_work_type", JOB_TITLE);
  await page.fill("#id_organization_name", "E2E Приход");
  await page.fill("#id_detailed_description", "Убрать территорию для E2E-проверки.");
  await page.getByRole("button", { name: "Далее →" }).click();
  await page.fill("#id_payment_amount", "1500");
  await page.fill("#id_max_workers", "1");
  await page.fill("#id_date_time", futureLocalDateTime(3));
  await page.getByRole("button", { name: "Далее →" }).click();
  await page.fill("#id_address", "ул. Тверская, 7");
  await page.fill("#id_city", "Москва");
  await page.getByRole("button", { name: "Сохранить" }).click();
  await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 20000 });
  const jobPath = new URL(page.url()).pathname;
  const body = await page.locator("body").innerText();
  if (!body.includes(JOB_TITLE)) {
    throw new Error("job title is missing on the detail page");
  }
  await context.close();
  return jobPath;
}

async function anonymousView(browser, jobPath) {
  const { context, page } = await newPage(browser);
  const events = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/analytics/event")) {
      try {
        events.push(request.postDataJSON());
      } catch (e) { /* ignore malformed */ }
    }
  });
  await page.goto(BASE + jobPath, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  if (!events.some((event) => event.event === "job_view")) {
    throw new Error("anonymous job_view beacon was not sent");
  }
  const before = events.length;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  if (events.length !== before) {
    throw new Error("anonymous view was counted twice within 24h");
  }
  await context.close();
}

async function themeToggle(browser) {
  const { context, page } = await newPage(browser);
  await page.goto(BASE + "/jobs", { waitUntil: "domcontentloaded" });
  await page.locator("#theme-toggle").click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await page.locator("#theme-toggle").click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
  await context.close();
}

async function apply(browser, jobPath) {
  const { context, page } = await login(browser, WORKER);
  await page.goto(BASE + jobPath, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Откликнуться" }).click();
  await page.waitForURL(/push=1/, { timeout: 20000 });
  const body = await page.locator("body").innerText();
  if (!body.includes("Отклик отправлен")) {
    throw new Error("application confirmation is missing");
  }
  await context.close();
}

async function acceptAndChat(browser, jobPath) {
  const { context, page } = await login(browser, EMPLOYER);
  await page.goto(BASE + "/my-applications?tab=received", { waitUntil: "domcontentloaded" });
  const row = page.locator("article").filter({ hasText: JOB_TITLE }).first();
  await row.waitFor({ state: "visible" });
  await row.getByRole("button", { name: "Принять", exact: true }).click();
  // Accept redirects to the job's applicants page; reload the received list.
  await page.waitForURL(/\/jobs\/[0-9a-f-]{36}\/applicants/, { timeout: 20000 });
  await page.goto(BASE + "/my-applications?tab=received", { waitUntil: "domcontentloaded" });
  const acceptedRow = page.locator("article").filter({ hasText: JOB_TITLE }).first();
  await acceptedRow.getByText("Принят", { exact: true }).waitFor({ timeout: 20000 });

  const chatLink = acceptedRow.getByRole("link", { name: "Чат" });
  const href = await chatLink.getAttribute("href");
  if (!href) throw new Error("chat link is missing after acceptance");
  await page.goto(BASE + href, { waitUntil: "domcontentloaded" });
  await page.fill('input[name="content"]', MESSAGE);
  await page.getByRole("button", { name: "Отправить" }).click();
  await page.waitForURL(/\/chat\/[0-9a-f-]{36}/, { timeout: 20000 });
  await page.getByText(MESSAGE, { exact: true }).waitFor({ timeout: 20000 });
  await context.close();
  return href;
}

async function workerSeesChat(browser, chatPath) {
  const { context, page } = await login(browser, WORKER);
  await page.goto(BASE + chatPath, { waitUntil: "domcontentloaded" });
  await page.getByText(MESSAGE, { exact: true }).waitFor({ timeout: 20000 });
  await context.close();
}

async function workerMarksComplete(browser) {
  const { context, page } = await login(browser, WORKER);
  await page.goto(BASE + "/my-applications?tab=sent", { waitUntil: "domcontentloaded" });
  const row = page.locator("article").filter({ hasText: JOB_TITLE }).first();
  await row.getByRole("button", { name: "Я выполнил" }).click();
  await page.waitForURL(/tab=sent/, { timeout: 20000 });
  await page.locator("article").filter({ hasText: JOB_TITLE }).first()
    .getByText("Выполнено", { exact: true }).waitFor({ timeout: 20000 });
  await context.close();
}

async function mobileLayout(browser, jobPath, chatPath) {
  const paths = [
    "/jobs", "/searches", "/profile", "/profile/sessions", "/my-jobs", "/my-applications",
    "/chats", "/notifications", "/notifications/settings", "/workers",
    jobPath,
  ];
  if (chatPath) paths.push(chatPath);
  for (const width of [360, 390]) {
    const { context, page } = await login(browser, EMPLOYER, { width, height: 844 });
    for (const path of paths) {
      await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
      const size = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      if (size.scroll > size.viewport + 1) {
        throw new Error(`${width}px ${path}: horizontal scroll ${size.scroll}/${size.viewport}`);
      }
    }
    await context.close();
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const started = Date.now();
    console.log("E2E " + BASE + "\n");

    console.log("▶ Регистрация");
    const email = await register(browser).catch((error) => {
      fail("registration", error);
      return null;
    });
    if (email) ok("новый пользователь зарегистрирован и получает подтверждение email");

    console.log("▶ Тема");
    await themeToggle(browser).catch((error) => fail("theme", error));
    if (!failures.some((f) => f.name === "theme")) {
      ok("тёмная тема переключается и сохраняется после reload");
    }

    console.log("▶ Задание");
    const jobPath = await createJob(browser).catch((error) => {
      fail("job create", error);
      return null;
    });
    if (jobPath) ok("работодатель создал задание: " + jobPath);

    if (jobPath) {
      console.log("▶ Анонимный просмотр");
      await anonymousView(browser, jobPath).catch((error) => fail("anonymous view", error));
      if (!failures.some((f) => f.name === "anonymous view")) {
        ok("анонимный просмотр учтён один раз за 24 часа");
      }

      console.log("▶ Отклик");
      await apply(browser, jobPath).catch((error) => fail("apply", error));
      if (!failures.some((f) => f.name === "apply")) ok("трудник откликнулся");

      console.log("▶ Принятие и чат");
      const chatPath = await acceptAndChat(browser, jobPath).catch((error) => {
        fail("accept/chat", error);
        return null;
      });
      if (chatPath) ok("работодатель принял отклик и написал в чат");

      if (chatPath) {
        console.log("▶ Чат у трудника");
        await workerSeesChat(browser, chatPath).catch((error) => fail("worker chat", error));
        if (!failures.some((f) => f.name === "worker chat")) ok("трудник видит сообщение в чате");

        console.log("▶ Подтверждение выполнения");
        await workerMarksComplete(browser).catch((error) => fail("worker complete", error));
        if (!failures.some((f) => f.name === "worker complete")) {
          ok("трудник отметил выполнение");
        }
      }

      console.log("▶ Мобильная вёрстка");
      await mobileLayout(browser, jobPath, chatPath).catch((error) => fail("mobile layout", error));
      if (!failures.some((f) => f.name === "mobile layout")) {
        ok("мобильная вёрстка без горизонтального скролла");
      }
    }

    const seconds = ((Date.now() - started) / 1000).toFixed(1);
    console.log("\nИтог: " + passed + " passed, " + failures.length + " failed, " + seconds + "s");
    if (failures.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
