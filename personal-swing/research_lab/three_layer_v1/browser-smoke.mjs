import {chromium} from "playwright";
import assert from "node:assert/strict";
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[];page.on("pageerror",e=>errors.push(e.message));
 await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
 await page.waitForFunction(()=>document.body.dataset.ready==="true",{},{timeout:60000});
 assert.equal(await page.locator("#symbol option").count(),477);
 assert.match(await page.locator("#status").textContent(),/477\/477/);
 assert.ok(await page.locator("#chart canvas").count()>0);
 await page.selectOption("#symbol","1");
 assert.match(await page.locator("#detail").textContent(),/DEMO002/);
 await page.selectOption("#symbol","0");
 assert.match(await page.locator("#detail").textContent(),/HOLD/);
 assert.equal(errors.length,0,errors.join("\n"));
 console.log("SYNTHETIC_BROWSER_477_CHART_HOLD_PASS");
}finally{await browser.close()}
