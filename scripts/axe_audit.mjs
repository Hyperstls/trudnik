/**
 * axe-core audit for public Trudnik pages (J108).
 * Run after: npm install --no-save playwright @axe-core/playwright
 *            npx playwright install --with-deps chromium
 */
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const base = (process.env.BASE_URL || 'https://xn--d1aigknli.xn--p1ai').replace(/\/$/, '');
const paths = ['/jobs', '/login', '/workers'];
const viewports = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
];

const browser = await chromium.launch({ headless: true });
const failures = [];
for (const viewport of viewports) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    locale: 'ru-RU',
  });
  const page = await context.newPage();
  for (const path of paths) {
    const response = await page.goto(base + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(800);
    if (!response || response.status() >= 400) {
      failures.push(`${viewport.name} ${path}: HTTP ${response ? response.status() : 'no response'}`);
      continue;
    }
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const critical = results.violations.filter((v) => v.impact === 'critical');
    if (critical.length) {
      for (const violation of critical) {
        failures.push(
          `${viewport.name} ${path}: ${violation.id} — ${violation.help} (${violation.nodes.length} nodes)`,
        );
      }
    } else {
      console.log(`axe OK ${viewport.name} ${path}`);
    }
  }
  await context.close();
}
await browser.close();
if (failures.length) {
  console.error('axe critical violations:\n' + failures.join('\n'));
  process.exit(1);
}
console.log('axe: no critical violations');
