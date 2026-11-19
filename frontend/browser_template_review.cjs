/* Run after the production build. The server opens a random port and a private temporary library. */
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const readline = require('node:readline');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE ||
  'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const fixture = spawn(path.join(root, '.wxq-runtime/Scripts/python.exe'), ['-u', 'frontend/browser_templates_fixture.py','--paginate'], {
    cwd: root, windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' }, stdio: ['ignore', 'pipe', 'inherit'],
  });
  const output = readline.createInterface({ input: fixture.stdout });
  let browser;
  try {
    const startup = await Promise.race([
      once(output, 'line').then(([line]) => JSON.parse(line)),
      once(fixture, 'exit').then(([code]) => { throw Error('Fixture exited with ' + code); }),
    ]);
    const base = 'http://127.0.0.1:' + startup.port;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH ||
      'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
    async function login(name) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
      await page.goto(base + '/admin');
      await page.getByLabel('用户名', { exact: true }).fill(name);
      await page.getByLabel('密码', { exact: true }).fill('fixture');
      await page.getByRole('button', { name: '登录', exact: true }).click();
      await page.getByRole('button', { name: '已知晓，稍后检查', exact: true }).click();
      await page.getByRole('button', { name: '模板库', exact: true }).click();
      return page;
    }
    const writer = await login('alice');
    await writer.getByText('关联资料已变化，待检查', { exact: true }).waitFor();
    assert.equal(await writer.getByRole('button', { name: '已检查，无需修改' }).count(), 0);
    assert.equal(await writer.getByRole('article',{name:'翻页组22',exact:true}).count(),0);
    await writer.getByLabel('搜索模板').fill('翻页组22');
    await writer.getByRole('button',{name:'批注话术1'}).click();
    const late=writer.getByRole('dialog',{name:'翻页组22 · 批注与记录'});
    await late.getByLabel('话术批注').fill('分页检查');await late.getByRole('button',{name:'发布批注'}).click();
    await late.locator('.template-feedback-thread p').filter({hasText:'分页检查'}).waitFor();
    await late.getByRole('button',{name:'定位到话术'}).click();
    await writer.waitForFunction(()=>document.activeElement?.getAttribute('data-feedback-utterance')==='zz_line_22');
    assert.equal(await writer.getByLabel('搜索模板').inputValue(),'');
    const before = '战斗即将开始，检查站位与装备。';
    const submitted = '编辑员提议先看站位。';
    const finalText = '开战前请再看一次站位。';
    const group = writer.getByRole('article', { name: '战前检查提醒', exact: true });
    await group.getByRole('button', { name: '批注话术1' }).click();
    const feedback = writer.getByRole('dialog', {name:'战前检查提醒 · 批注与记录'});
    await feedback.getByLabel('话术批注', {exact:true}).fill('建议检查开战时机');
    await feedback.getByRole('button', {name:'发布批注'}).click();
    await feedback.locator('.template-feedback-thread p').filter({hasText:'建议检查开战时机'}).waitFor();
    assert.equal(await feedback.getByRole('button', {name:'关闭批注',exact:true}).count(),0);
    await feedback.getByRole('button', {name:'关闭战前检查提醒 · 批注与记录'}).click();
    await writer.getByRole('searchbox').fill('不会匹配的模板');
    await writer.getByRole('button', {name:'全库批注与记录'}).click();
    await writer.locator('.template-feedback-thread').filter({hasText:'建议检查开战时机'}).getByRole('button', {name:'定位到话术'}).click();
    assert.equal(await writer.getByRole('searchbox').inputValue(),'');
    await writer.waitForFunction(()=>document.activeElement?.getAttribute('data-feedback-utterance')==='prepare_line');
    await group.getByRole('button', { name: '编辑模板战前检查提醒', exact: true }).click();
    const draft = writer.getByRole('dialog', { name: '提议修改模板', exact: true });
    await draft.getByLabel('模板组名称', { exact: true }).fill('开战前三项检查');
    await draft.getByRole('textbox', { name: '话术 1', exact: true }).fill(submitted);
    await draft.getByRole('button', { name: '提交修改提案', exact: true }).click();
    await draft.waitFor({ state: 'hidden' });
    await group.getByText(before, { exact: true }).waitFor();

    const bob=await login('bob');
    await bob.getByRole('button',{name:'我的提案'}).click();
    await bob.getByText('暂无模板提案。').waitFor();
    await bob.getByRole('button',{name:'关闭我的模板提案'}).click();
    await bob.getByRole('button',{name:'全库批注与记录'}).click();
    const bthread=bob.locator('.template-feedback-thread').filter({hasText:'建议检查开战时机'});
    await bthread.getByLabel('回复批注').fill('另一位编写员已复核');
    await bthread.getByRole('button',{name:'发送回复'}).click();
    await bthread.locator('p').filter({hasText:'另一位编写员已复核'}).waitFor();
    assert.equal(await bthread.getByRole('button',{name:'关闭批注',exact:true}).count(),0);
    const admin = await login('reviewer');
    await admin.getByRole('button', { name: '已检查，无需修改' }).waitFor();
    const currentGroup = admin.getByRole('article', { name: '战前检查提醒', exact: true });
    await admin.getByRole('button',{name:'全库批注与记录'}).click();
    const inbox=admin.getByRole('dialog',{name:'模板批注与记录'});
    const thread=inbox.locator('.template-feedback-thread').filter({hasText:'建议检查开战时机'});
    await thread.getByLabel('回复批注').fill('已核对，保留原句');
    await thread.getByRole('button',{name:'发送回复'}).click();
    await inbox.locator('.template-feedback-thread p').filter({hasText:'已核对，保留原句'}).waitFor();
    await thread.getByRole('button',{name:'关闭批注',exact:true}).click();
    await thread.waitFor({state:'hidden'});
    await inbox.getByLabel('批注状态').selectOption('closed');
    await inbox.getByRole('button',{name:'重开批注'}).click();
    await inbox.getByText('没有符合条件的批注。').waitFor();
    await inbox.getByRole('button',{name:'关闭模板批注与记录'}).click();
    await currentGroup.getByRole('button', { name: '编辑模板战前检查提醒', exact: true }).click();
    const formalDraft = admin.getByRole('dialog', { name: '编辑模板', exact: true });
    await formalDraft.getByLabel('模板组名称', { exact: true }).fill('正式版战前检查');
    await formalDraft.getByRole('button', { name: '保存模板', exact: true }).click();
    await formalDraft.waitFor({ state: 'hidden' });

    await writer.getByRole('button', { name: '我的提案', exact: true }).click();
    const writerReview = writer.getByRole('dialog', { name: '我的模板提案', exact: true });
    await writerReview.getByText('等待管理员核对正式版本。', { exact: true }).waitFor();
    assert.equal(await writerReview.getByRole('button', { name: '已核对当前版本，保留提案内容' }).count(), 0);
    assert.equal(await writerReview.getByRole('button', { name: '核对并修改提案' }).count(), 0);
    await admin.getByRole('button', { name: '提案审核', exact: true }).click();
    const review = admin.getByRole('dialog', { name: '模板提案审核', exact: true });
    await review.getByText('提案讨论（0）').click();
    await review.getByLabel('讨论内容').fill('仅供作者和管理员核对');
    await review.getByRole('button',{name:'发表讨论'}).click();
    await review.locator('p').filter({hasText:'仅供作者和管理员核对'}).waitFor();
    const privateHistory=await (await bob.request.get(base+'/api/templates/history?group_id=prepare_example')).text();
    assert(!privateHistory.includes('仅供作者和管理员核对'));
    assert(!privateHistory.includes(submitted));
    await review.getByRole('button', { name: '核对并修改提案', exact: true }).click();
    const edit = admin.getByRole('dialog', { name: '修改模板提案', exact: true });
    const text = edit.getByRole('textbox', { name: '话术 1', exact: true });
    assert.equal(await text.inputValue(), submitted);
    await text.fill(finalText);
    await edit.getByRole('button', { name: '保存审核稿', exact: true }).click();
    await review.waitFor();
    const readFormal = async () => {
      const response = await admin.request.get(base + '/api/templates');
      assert.equal(response.status(), 200);
      return (await response.json()).groups.find(record => record.id === 'prepare_example');
    };
    assert.equal((await readFormal()).utterances[0].text, before);
    await review.getByRole('checkbox', { name: '采纳此项话术修改', exact: true }).uncheck();
    const approve = review.getByRole('button', { name: '采纳勾选修改', exact: true });
    await approve.click();
    await review.getByText('部分已采纳 · 待继续审核', { exact: true }).waitFor();
    const partial = await readFormal();
    assert.equal(partial.name, '开战前三项检查');
    assert.equal(partial.utterances[0].text, before);
    await approve.click();
    await review.getByText('已采纳', { exact: true }).waitFor();
    assert.equal((await readFormal()).utterances[0].text, finalText);
    await review.getByText('原始提案', { exact: true }).click();
    await review.getByText(submitted, { exact: false }).filter({ visible: true }).first().waitFor();
    await review.getByRole('button', { name: '关闭模板提案审核', exact: true }).click();
    await admin.getByRole('article', { name: '开战前三项检查', exact: true }).getByText(finalText, { exact: true }).waitFor();
    await admin.getByRole('button',{name:'全库批注与记录'}).click();
    await inbox.getByRole('button',{name:'管理员操作记录'}).click();
    await inbox.getByText(/部分采纳 · reviewer/).waitFor();
    await inbox.getByRole('button',{name:'关闭模板批注与记录'}).click();
    const publishedHistory=(await (await bob.request.get(base+'/api/templates/history?group_id=prepare_example')).json()).items;
    assert(publishedHistory.some(h=>h.action==='approve_partial'));
    assert(!JSON.stringify(publishedHistory).includes(submitted));
    const document=await (await admin.request.get(base+'/api/templates/export?group_ids=prepare_example')).json();
    document.groups[0].name='管理员导入审核测试'; delete document.groups[0].id;
    await admin.getByRole('button',{name:'导入 JSON'}).click();
    const importer=admin.getByRole('dialog',{name:'导入话术模板库'});
    await importer.getByLabel('或粘贴 JSON').fill(JSON.stringify(document));
    await importer.getByRole('button',{name:'检查并预览'}).click();
    await importer.getByRole('button',{name:'确认提交导入提案'}).click();
    await importer.waitFor({state:'hidden'});
    const pending=(await (await admin.request.get(base+'/api/templates/proposals')).json()).find(p=>p.source==='web-import');
    assert.equal(pending.status,'pending');
    assert(!(await (await admin.request.get(base+'/api/templates')).json()).groups.some(g=>g.name==='管理员导入审核测试'));
    await admin.getByRole('button',{name:'提案审核',exact:true}).click();
    const pendingCard=review.locator('.template-proposal').filter({hasText:'管理员导入审核测试'});
    await pendingCard.getByRole('button',{name:'采纳勾选修改'}).click();
    await pendingCard.getByText('已采纳',{exact:true}).waitFor();
    await review.getByRole('button',{name:'关闭模板提案审核'}).click();
    const importedId=pending.changes.find(c=>c.kind==='group').id;
    const originalApproval=(await (await admin.request.get(base+'/api/templates/history?group_id='+importedId)).json()).items.find(row=>row.action==='approve');
    assert.deepEqual(originalApproval.submitted,originalApproval.reviewed);
    assert.deepEqual(originalApproval.original_submission,originalApproval.reviewed);
    assert.equal(originalApproval.after.name,'管理员导入审核测试');
    admin.once('dialog', dialog=>dialog.accept());
    await admin.getByRole('article',{name:'开战前三项检查',exact:true}).getByRole('button',{name:'删除模板开战前三项检查'}).click();
    await admin.getByRole('article',{name:'开战前三项检查',exact:true}).waitFor({state:'hidden'});
    await admin.getByRole('button',{name:'全库批注与记录'}).click();
    const deleted=inbox.locator('.template-feedback-thread').filter({hasText:'建议检查开战时机'});
    await deleted.getByText('批注对象已删除，以下为当时原文。').waitFor();
    await deleted.getByText(before,{exact:true}).waitFor();
    assert.equal(await deleted.getByRole('button',{name:'定位到话术'}).count(),0);
    const viewer=await browser.newPage();
    await viewer.request.post(base+'/api/auth/login',{data:{username:'reader',password:'fixture'},headers:{Origin:base}});
    await viewer.goto(base+'/admin');await viewer.getByRole('button',{name:'模板库',exact:true}).click();
    await viewer.getByRole('heading',{name:'话术模板库',exact:true}).waitFor();
    assert.equal(await viewer.getByRole('button',{name:'全库批注与记录'}).count(),0);
    assert.equal((await viewer.request.get(base+'/api/templates/comments')).status(),403);
    await viewer.waitForLoadState('networkidle');
    console.log('Passed two-writer formal discussion, private proposal discussion, page-25 focus, closure and reopening, original text after deletion, partial and final review history, admin default import, and viewer permissions.');
  } finally {
    if (browser) await browser.close();
    output.close();
    fixture.kill();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
