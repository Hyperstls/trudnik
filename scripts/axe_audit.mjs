/**
 * axe-core audit for Trudnik pages (J108).
 * Public mode (default): critical-only gate for public pages.
 * Auth mode (AXE_AUTH=1): logs in an E2E user and gates authenticated pages on
 * both critical and serious violations (R045).
 * Run after: npm install --no-save playwright @axe-core/playwright
 *            npx playwright install --with-deps chromium
 */
import { writeFileSync } from 'node:fs';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const authMode = process.env.AXE_AUTH === '1';
const base = (
  (authMode ? process.env.E2E_BASE_URL : process.env.BASE_URL) ||
  'https://xn--d1aigknli.xn--p1ai'
).replace(/\/$/, '');
const publicPaths = [
  '/', '/jobs', '/login', '/workers', '/employers', '/register',
  '/search?q=test', '/support', '/info', '/faq', '/app',
  '/terms', '/privacy', '/safety', '/offline',
];
const authPaths = [
  '/profile', '/profile/sessions', '/my-applications', '/my-jobs', '/chats',
  '/notifications', '/notifications/settings', '/searches', '/favorites',
  '/favorite-jobs', '/favorite-people', '/my-ratings', '/blacklist',
  '/invitations', '/jobs/new',
];
const paths = authMode ? authPaths : publicPaths;
const email = process.env.E2E_EMAIL || 'e2e-employer@example.com';
const password = process.env.E2E_PASSWORD || 'Aa1!aaaa'; // pragma: allowlist secret
const viewports = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
];

const themes = [
  { name: 'light', colorScheme: 'light' },
  { name: 'dark', colorScheme: 'dark' },
];

async function login(page) {
  await page.goto(base + '/login', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.fill('#email', email);
  await page.fill('#password', password);
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 20000 });
}

const browser = await chromium.launch({ headless: true });
const failures = [];
const warnings = [];
for (const theme of themes) {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      locale: 'ru-RU',
      colorScheme: theme.colorScheme,
    });
    // Let the page follow the requested color scheme, not a previous choice.
    await context.addInitScript(() => {
      try { localStorage.removeItem('trudnik-theme'); } catch (e) { /* ignore */ }
    });
    const page = await context.newPage();
    if (authMode) await login(page);
    for (const path of paths) {
      const label = `${theme.name} ${viewport.name} ${path}`;
      const response = await page.goto(base + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(800);
      if (!response || response.status() >= 400) {
        failures.push(`${label}: HTTP ${response ? response.status() : 'no response'}`);
        continue;
      }
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const critical = results.violations.filter((v) => v.impact === 'critical');
      const serious = results.violations.filter((v) => v.impact === 'serious');
      if (authMode) {
        for (const violation of [...critical, ...serious]) {
          failures.push(
            `${label}: ${violation.impact} ${violation.id} — ${violation.help} (${violation.nodes.length} nodes)`,
          );
        }
      } else {
        for (const violation of serious) {
          warnings.push(
            `${label}: ${violation.id} — ${violation.help} (${violation.nodes.length} nodes)`,
          );
        }
        for (const violation of critical) {
          failures.push(
            `${label}: ${violation.id} — ${violation.help} (${violation.nodes.length} nodes)`,
          );
        }
      }
      if (!critical.length && !(authMode && serious.length)) {
        console.log(`axe OK ${label}`);
      }
    }
    await context.close();
  }
}
await browser.close();
writeFileSync(
  'axe-report.json',
  JSON.stringify({
    base,
    mode: authMode ? 'auth' : 'public',
    themes: themes.map((t) => t.name),
    generated_at: new Date().toISOString(),
    failures,
    warnings,
  }, null, 2),
);
if (warnings.length) {
  console.warn('axe serious warnings:\n' + warnings.join('\n'));
}
if (failures.length) {
  console.error('axe violations:\n' + failures.join('\n'));
  process.exit(1);
}
console.log(
  'axe: no violations' + (warnings.length ? ` (${warnings.length} serious warnings)` : ''),
);
