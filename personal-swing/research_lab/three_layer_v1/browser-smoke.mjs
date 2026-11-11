import {chromium} from "playwright";
import assert from "node:assert/strict";
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({locale:"tr-TR",viewport:{width:390,height:844}});
 const errors=[];page.on("pageerror",e=>{errors.push(e.message);console.log("PAGE_ERROR",e.message)});page.on("console",m=>{if(m.type()==="error"||m.type()==="warning")console.log("BROWSER",m.type(),m.text())});page.on("requestfailed",r=>console.log("REQUEST_FAILED",r.url(),r.failure()?.errorText));page.on("response",r=>{if(r.status()>=400)console.log("HTTP",r.status(),r.url())});
 await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
 console.log("BROWSER_LOCALE",await page.evaluate(()=>[navigator.language,Intl.DateTimeFormat().resolvedOptions().locale]));
 await page.waitForFunction(()=>["true","false"].includes(document.body.dataset.ready),{},{timeout:60000});
 assert.equal(await page.locator("body").getAttribute("data-ready"),"true",await page.locator("main > #xray-status").textContent());
 assert.equal(await page.locator("#symbol option").count(),477);
 assert.match(await page.locator("main > #xray-status").textContent(),/477\/477/);
 assert.ok(await page.locator("#chart canvas").count()>0);
 await page.selectOption("#symbol","1");
 assert.match(await page.locator("#detail").textContent(),/DEMO002/);
 await page.selectOption("#symbol","0");
 assert.match(await page.locator("#detail").textContent(),/HOLD/);
 assert.equal(errors.length,0,errors.join("\n"));
 console.log("SYNTHETIC_BROWSER_477_CHART_HOLD_PASS");
}finally{await browser.close()}
