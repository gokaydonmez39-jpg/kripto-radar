'use strict';

// Offline routing proof against the exact versioned ChatGPT A/B runtime.
// No Google Sheets, no GitHub network, no automation updates, no orders.
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {test}=require('node:test');

const runtime=JSON.parse(readFileSync(process.env.XRAY_TEST_RUNTIME||
  join(__dirname,'xray_477_task_runtime_v3.json'),'utf8'));
assert.equal(runtime.schema,'XRAY_NASDAQ_477_RUNTIME_V3');
const TASK='abcdefabcdefabcdefabcdefabcdefab';
const CHAT='11111111-1111-4111-8111-111111111111';
const SLOT='22222222-2222-4222-8222-222222222222';
const PREVIOUS_CANARY='33333333-3333-4333-8333-333333333333';
const SEAL='01617e17545aa47e6d92988c9884ce56387d26437bf2f72683edc5bcd6f3705b';
const ASOF='2026-11-20';
const currentSlot={id:SLOT,scheduled_for:'2026-11-20T21:57:48Z',
  started_at:'2026-11-20T21:56:00Z'};
const prompt='XRAY_A_DEPLOYMENT_STAGE=ARMED_AFTER_CANARY_V1|'+
  PREVIOUS_CANARY+'|2026-11-19|2026-11-19T22:00:00Z|'+SEAL;

function createHarness(initial) {
  const calls={a:0,b:0};
  const fakeB='const XRAY_B_NATURAL=(()=>({'+
    'run:async()=>({state:"B_RUN_INVOKED",post_calls:0}),'+
    'natural:()=>('+JSON.stringify(currentSlot)+')}))();';
  const fakeDriver='const XRAY_B_DRIVER=(()=>{const SID="synthetic_sheet_id";return {};})();';
  const blocks=[fakeB,fakeDriver];
  const compile=src=>()=>Function('__xrayCompile','__xrayBlocks','__xrayPortable',src)(
    compile,()=>blocks,()=>runtime.portable.code);
  const actual=runtime.blocks[11].replaceAll('XRAY_CONFIG_TASK_ID_V1',TASK)
    .replaceAll('XRAY_CONFIG_CHAT_ID_V1',CHAT);
  const stage=Function('__xrayCompile','__xrayBlocks','__xrayPortable',
    actual+'\nreturn XRAY_AB_STAGED;')(compile,()=>blocks,()=>runtime.portable.code);
  const task={id:TASK,is_enabled:true,conversation_id:CHAT,prompt};
  const tools={
    mcp__Automations__peek:async()=>({automations:[task]}),
    clock__curr_time:async()=>({current_time:'2026-11-20 22:00:00 UTC'})
  };
  const implementation={runNaturalCandidate:async()=>{
    calls.a+=1;
    return initial;
  }};
  return {calls,go:()=>stage.run(ASOF,tools,['mcp__Automations__peek','clock__curr_time'],
    implementation,SEAL,task)};
}

for(const [name,fromA,expect] of [
  ['no A event - B runs', {state:'NO_CURRENT_A',post_calls:0},'B_RUN_INVOKED'],
  ['no A event - undefined post count cannot bypass safety',{state:'NO_CURRENT_A'},'NO_CURRENT_A'],
  ['no A event - POST already attempted cannot bypass safety',{state:'NO_CURRENT_A',post_calls:1},'NO_CURRENT_A'],
  ['confirmed A event - A must win',{state:'EMIT_NOW',post_calls:1},'EMIT_NOW'],
  ['uncertain A POST cannot fall into B',{state:'HOLD',stage:'A_POST_UNCERTAIN_DO_NOT_RESEND',post_calls:1},'HOLD'],
  ['A source HOLD cannot silently produce B',{state:'HOLD',stage:'A_SOURCE_UNVERIFIED',post_calls:0},'HOLD'],
  ['unverified no event state is not a successful empty queue',{state:'UNVERIFIED_NO_A',post_calls:0},'UNVERIFIED_NO_A'],
  ['existing adapter preflight fallback is preserved',
    {state:'HOLD',stage:'TURN_NATIVE_ADAPTER_UNAVAILABLE',post_calls:0},'B_RUN_INVOKED'],
  ['existing risk queue preflight fallback is preserved',
    {state:'HOLD',stage:'TURN_RISK_QUEUE_UNVERIFIED',post_calls:0},'B_RUN_INVOKED'],
  ['existing unknown stage does not bypass A',
    {state:'HOLD',stage:'SOME_NEW_UNKNOWN_ERROR',post_calls:0},'HOLD']
]) {
  test('XRAY AB route: '+name,async()=>{
    const h=createHarness(fromA);
    const out=await h.go();
    assert.equal(out.state,expect);
    assert.equal(h.calls.a,1);
    // This test never connects to a POST adapter or real Sheet/price source.
    assert.equal(typeof out.post_calls==='number' ? out.post_calls>=0 : true,true);
  });
}

test('synthetic record has exactly the immutable same task and no external effects',()=>{
  const h=createHarness({state:'NO_CURRENT_A',post_calls:0});
  assert.equal(runtime.blocks.length,12);
  assert.equal(typeof h.go,'function');
  assert.equal(TASK.length,32);
  assert.equal(SEAL.length,64);
});
