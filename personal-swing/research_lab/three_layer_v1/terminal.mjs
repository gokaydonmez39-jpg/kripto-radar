import "./node_modules/@perspective-dev/viewer/dist/cdn/perspective-viewer.js";
import "./node_modules/@perspective-dev/viewer-datagrid/dist/cdn/perspective-viewer-datagrid.js";
import perspective from "./node_modules/@perspective-dev/client/dist/cdn/perspective.js";
import {createChart,CandlestickSeries,LineSeries,LineStyle} from "./node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.mjs";
// No private data, credentials, connector, network API or production input.
const rows=Array.from({length:477},(_,i)=>({symbol:"DEMO"+String(i+1).padStart(3,"0"),score:40+i%61,status:["AL","IZLE","ELE"][i%3],quality:i%5===0?"HOLD":i%3===0?"NATIVE":"RESEARCH_CLOSE_ONLY",asof:"SYNTHETIC"}));
const status=document.querySelector("#status"),select=document.querySelector("#symbol"),detail=document.querySelector("#detail");
const dates=["2026-10-26","2026-10-27","2026-10-28","2026-10-29","2026-10-30","2026-11-02","2026-11-03","2026-11-04","2026-11-05","2026-11-06","2026-11-09","2026-11-10"];
try{
 const worker=await perspective.worker();
 const table=await worker.table(rows,{name:"xray_demo"});
 const viewer=document.querySelector("#viewer");
 await viewer.load(worker);
 await viewer.restore({table:"xray_demo",settings:true});
 const count=await table.size();
 if(count!==477)throw new Error("DEMO_SCOPE_MISMATCH");
 const chart=createChart(document.querySelector("#chart"),{autoSize:true});
 const candle=chart.addSeries(CandlestickSeries);
 const forecast=chart.addSeries(LineSeries,{color:"#8555b7",lineStyle:LineStyle.Dashed,lastValueVisible:false,priceLineVisible:false});
 let levels=[];
 function render(){
   const i=Number(select.value),r=rows[i],base=80+i%30;
   const bars=dates.map((time,j)=>({time,open:base+j*.4,high:base+j*.4+1.1,low:base+j*.4-.8,close:base+j*.4+.3}));
   candle.setData(bars);
   for(const line of levels)candle.removePriceLine(line);
   const ref=bars.at(-1).close;
   levels=[candle.createPriceLine({price:ref-4,color:"#b84545",lineStyle:LineStyle.Dashed,title:"DEMO STOP"}),candle.createPriceLine({price:ref+8,color:"#16855b",lineStyle:LineStyle.Dashed,title:"DEMO 2R"})];
   forecast.setData(r.quality==="HOLD"?[]:[{time:"2026-11-11",value:ref+.5},{time:"2026-11-17",value:ref+1.8},{time:"2026-11-27",value:ref+3.2}]);
   chart.timeScale().fitContent();
   detail.textContent=r.symbol+" · "+r.quality+" · Sentetik skor "+r.score+"/100";
 }
 for(let i=0;i<rows.length;i++){const o=document.createElement("option");o.value=String(i);o.textContent=rows[i].symbol;select.append(o)}
 select.addEventListener("change",render);render();
 status.textContent="477/477 sentetik tablo ve grafik hazır";document.body.dataset.ready="true";
}catch(error){status.textContent="HOLD: demo yüklenemedi";document.body.dataset.ready="false";console.error(error);}
