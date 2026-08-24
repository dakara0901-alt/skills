// Driver for the 100-skills dashboard (100-skills/index.html).
//
// The dashboard is a single self-contained static HTML file — no build,
// no server, no external requests. This driver opens it in headless
// Chromium (Playwright), optionally drives the search box / category
// chips, verifies the visible-card count, and writes a screenshot.
//
// Playwright is installed globally in this container, so run with:
//   NODE_PATH=/opt/node22/lib/node_modules node driver.mjs <cmd> [arg]
//
// Commands:
//   smoke              full smoke test: default view + search + category
//                      filter, asserts counts, checks console errors,
//                      exits non-zero on any failure. Writes 3 shots.
//   shot               screenshot the default (all-100) view
//   search <term>      type <term> into the search box, screenshot
//   cat <NN>           click category chip NN (01..10), screenshot
//
// Env:
//   SHOTS_DIR   where screenshots land (default /tmp/shots)
//   HTML_PATH   path to index.html (default: ../../../index.html,
//               i.e. the 100-skills/ dir this skill lives under)

import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

// Playwright is installed globally in this container, not in a local
// node_modules. ESM `import` ignores NODE_PATH, so resolve it through a
// CommonJS require rooted at the global module dir.
const require = createRequire(import.meta.url);
const GLOBAL_MODULES =
  process.env.NODE_PATH || '/opt/node22/lib/node_modules';
const { chromium } = require(resolve(GLOBAL_MODULES, 'playwright'));

const here = dirname(fileURLToPath(import.meta.url));
const htmlPath = process.env.HTML_PATH
  ? resolve(process.env.HTML_PATH)
  : resolve(here, '../../../index.html');
const shotsDir = process.env.SHOTS_DIR || '/tmp/shots';
mkdirSync(shotsDir, { recursive: true });

const [cmd = 'smoke', arg] = process.argv.slice(2);

// visible (non-.hide) card count + the header counter the app renders
async function counts(page) {
  return page.evaluate(() => ({
    visible: document.querySelectorAll('.card:not(.hide)').length,
    counter: parseInt(document.getElementById('count-n').textContent, 10),
    total: document.querySelectorAll('.card').length,
  }));
}

async function shot(page, name) {
  const p = `${shotsDir}/${name}.png`;
  await page.screenshot({ path: p, fullPage: true });
  console.log(`  screenshot → ${p}`);
  return p;
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT FAILED: ${msg}`);
  console.log(`  ok: ${msg}`);
}

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
const consoleErrors = [];
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
page.on('pageerror', (e) => consoleErrors.push(String(e)));

try {
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  await page.waitForSelector('.card');

  if (cmd === 'shot') {
    console.log('== default view ==');
    console.log('  counts:', await counts(page));
    await shot(page, 'default');
  } else if (cmd === 'search') {
    const term = arg ?? '';
    console.log(`== search "${term}" ==`);
    await page.fill('#q', term);
    await page.waitForTimeout(150);
    console.log('  counts:', await counts(page));
    await shot(page, `search-${term.replace(/[^\w]+/g, '_') || 'empty'}`);
  } else if (cmd === 'cat') {
    const nn = arg ?? '01';
    console.log(`== category ${nn} ==`);
    await page.click(`.chip[data-cat="${nn}"]`);
    await page.waitForTimeout(150);
    console.log('  counts:', await counts(page));
    await shot(page, `cat-${nn}`);
  } else if (cmd === 'smoke') {
    console.log('== smoke: default view ==');
    let c = await counts(page);
    console.log('  counts:', c);
    assert(c.total === 100, '100 cards in the DOM');
    assert(c.visible === 100, 'all 100 visible by default');
    assert(c.counter === 100, 'header counter reads 100');
    await shot(page, 'smoke-1-default');

    console.log('== smoke: search "SEO" ==');
    await page.fill('#q', 'SEO');
    await page.waitForTimeout(150);
    c = await counts(page);
    console.log('  counts:', c);
    assert(c.visible > 0 && c.visible < 100, 'search narrows the list');
    assert(c.counter === c.visible, 'counter matches visible cards');
    await shot(page, 'smoke-2-search-SEO');

    console.log('== smoke: clear search + filter category 08 ==');
    await page.fill('#q', '');
    await page.click('.chip[data-cat="08"]');
    await page.waitForTimeout(150);
    c = await counts(page);
    console.log('  counts:', c);
    assert(c.visible === 10, 'category 08 shows its 10 skills');
    assert(c.counter === 10, 'counter reads 10');
    await shot(page, 'smoke-3-cat-08');

    console.log('== console errors ==');
    console.log('  ', consoleErrors.length ? consoleErrors : 'none');
    assert(consoleErrors.length === 0, 'no console/page errors');
    console.log('\nSMOKE PASSED');
  } else {
    throw new Error(`unknown command: ${cmd}`);
  }
} catch (err) {
  console.error('\nFAILED:', err.message);
  if (consoleErrors.length) console.error('console errors:', consoleErrors);
  process.exitCode = 1;
} finally {
  await browser.close();
}
