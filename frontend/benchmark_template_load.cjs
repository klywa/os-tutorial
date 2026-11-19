// Run from the project root with the local supervisor and both servers available.
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const executablePath = process.env.CHROMIUM_PATH || 'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe';

async function enterAndFilter(page) {
  const start = Date.now();
  await page.getByRole('button', {name:'模板库', exact:true}).click();
  await page.locator('.template-group').first().waitFor();
  const search = page.getByRole('searchbox', {name:'搜索模板'});
  await search.fill('周瑜');
  await search.fill('');
  return Date.now() - start;
}

async function measure(page, port, run, mode) {
  const start = Date.now();
  await page.goto('http://127.0.0.1:' + port, {waitUntil:'domcontentloaded'});
  const ready = page.getByRole('button', {name:'导出整篇', exact:true});
  const back = page.getByRole('button', {name:'对局助手', exact:true});
  await ready.waitFor();
  const home = Date.now() - start;
  const template = await enterAndFilter(page);
  await back.click();
  await ready.waitFor();
  const revisit = await enterAndFilter(page);
  const api = await page.evaluate(() => performance.getEntriesByType('resource')
    .filter(entry => entry.name.includes('/api/') && !entry.name.includes('/images/'))
    .map(entry => [entry.name.split('/api/')[1].split('?')[0], Math.round(entry.duration), entry.decodedBodySize]));
  await back.click();
  await ready.waitFor();
  return {port, run, mode, home, template, revisit, api};
}

async function main() {
  const destination = process.argv[2];
  if (!destination) throw new Error('请提供新的 JSONL 输出路径');
  fs.writeFileSync(destination, '', {flag:'wx'});
  const browser = await chromium.launch({headless:true, executablePath});
  try {
    for (const port of [5173, 8765]) {
      for (let run = 0; run < 3; run++) {
        const context = await browser.newContext();
        const page = await context.newPage();
        page.setDefaultTimeout(150000);
        for (const mode of ['cold','warm']) {
          const result = await measure(page, port, run, mode);
          fs.appendFileSync(destination, JSON.stringify(result) + '\n');
          console.log(port, run, mode, result.home, result.template, result.revisit);
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => {console.error(error); process.exitCode = 1;});
