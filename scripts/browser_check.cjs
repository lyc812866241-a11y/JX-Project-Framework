// Runs only against the supplied local fixture. No external website/network.
const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const {chromium} = require(process.env.JX_PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const report = process.argv[2];
  const browser = await chromium.launch({headless:true, ...(process.env.JX_BROWSER_EXECUTABLE ? {executablePath:process.env.JX_BROWSER_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport:{width:960,height:640}});
  let clicked = false, visibleAtCenter = false;
  const url = pathToFileURL(path.resolve('index.html')).href;
  try {
    await page.goto(url);
    visibleAtCenter = await page.locator('#add').evaluate(el => {const r=el.getBoundingClientRect(); return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===el;});
    try {await page.locator('#add').click({timeout:1500}); clicked = await page.locator('#count').innerText() === '1';} catch (_) {}
    await page.screenshot({path:path.join(path.dirname(report),'screen.png')});
    fs.writeFileSync(report,JSON.stringify({visibleAtCenter,clicked,url,viewport:{width:960,height:640},browser:browser.version(),action:'click #add once; #count must become 1',build:'local file bound by runner snapshot'},null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
