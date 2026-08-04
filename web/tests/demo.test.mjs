import test from "node:test";
import assert from "node:assert/strict";
import { demoR, DEMO_WEIGHTS, audienceFit, marketFit } from "../src/linkverse/demo/demoScoring.ts";
import { demoUrl, inferDomain, parseDemoState } from "../src/linkverse/demo/demoState.ts";

test("classifies supported products and rejects standalone football", () => {
  assert.equal(inferDomain("sun cream"), "sunscreen");
  assert.equal(inferDomain("축구화 launch"), "soccer_equipment");
  assert.equal(inferDomain("football"), null);
});
test("state survives URL round trip and represents browser history steps", () => {
  const states = [
    {view:"product",productInput:"",audienceInput:""},
    {view:"audience",domain:"sunscreen",productInput:"sun cream",audienceInput:""},
    {view:"market",domain:"sunscreen",productInput:"sun cream",audienceInput:"Gen Z"},
    {view:"scope",domain:"sunscreen",productInput:"sun cream",audienceInput:"Gen Z",market:"KR"},
  ];
  for (const state of states) {
    const parsed=parseDemoState(demoUrl(state));
    assert.equal(parsed.view,state.view); assert.equal(parsed.productInput,state.productInput);
    assert.equal(parsed.audienceInput,state.audienceInput); assert.equal(parsed.domain,state.domain); assert.equal(parsed.market,state.market);
  }
  assert.equal(parseDemoState(demoUrl(states.at(-2))).view, "market");
});
test("Demo R uses all three positive weights and clamps to 0..100", () => {
  assert.deepEqual(DEMO_WEIGHTS,{product:0.55,audience:0.30,market:0.15});
  assert.equal(demoR(10,20,30),16);
  assert.ok(demoR(50,50,100)>demoR(50,50,0));
  assert.ok(demoR(50,100,50)>demoR(50,0,50));
  assert.equal(demoR(500,500,500),100);
});
test("metadata audience and market fit react to conditions",()=>{
  const candidate={channel_id:"x",title:"Gen Z skincare routine",country:"KR",contentLanguage:"ko",P:50,productRelevance:50,videos:[]};
  assert.ok(audienceFit(candidate,"Gen Z")>0); assert.equal(marketFit(candidate,"KR"),100); assert.equal(marketFit(candidate,"US"),0);
});
