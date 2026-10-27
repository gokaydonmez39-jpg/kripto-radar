// Offline NASDAQ synthetic contract. Never processes live private account data.
module.exports=class NasdaqOfflineFixture {
  id(){ return "nasdaq-local-evidence-fixture"; }
  async callApi(prompt){
    let x;
    try { x=JSON.parse(prompt); } catch { return {output:"BLOCKED_MALFORMED"}; }
    const fail=(code)=>({output:"BLOCKED_"+code});
    if(x.scope!=="NASDAQ_477"||x.final!==true||x.valid!==477)return fail("COVERAGE");
    if(x.asof!==x.final_asof)return fail("ASOF");
    if(!x.unique||x.previously_requested)return fail("DEDUP");
    if(!x.source_verified||!x.sheet_readback)return fail("EVIDENCE");
    if(![x.close,x.stop,x.target].every(n=>typeof n==="number"&&Number.isFinite(n)))return fail("BAD_PRICE");
    if(!(x.stop>0&&x.stop<x.close&&x.close<x.target))return fail("GEOMETRY");
    if(typeof x.symbol!=="string"||!/^[A-Z]{1,5}$/.test(x.symbol))return fail("SYMBOL");
    return {output:"XRAY NASDAQ | "+x.symbol+" | "+x.asof+
      " | YENİ TEKNİK AL ÖN ADAYI; IEX referans "+x.close+
      "; Teorik stop "+x.stop+"; Teorik hedef "+x.target+
      "; Araştırma amaçlı, emir yok."};
  }
};
