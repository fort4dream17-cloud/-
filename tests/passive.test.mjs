import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePassive,passiveRanking,passiveMoney,historyWindow} from '../dist/passive.js';
const row=(code,net,extra={})=>({code,name:code,date:'2026-10-29',net,adv20:1000,adv_pct:net/10,partial:false,...extra});
const data=stocks=>({schema_version:1,meta:{data_kind:'real',unit:'KRW',as_of:'2026-10-29'},stocks});
test('ETF publication format rejects false ADV denominators, duplicate identities and example data',()=>{
 assert.throws(()=>validatePassive(data([row('005930',100,{adv_pct:99})])),/산식/);
 assert.throws(()=>validatePassive(data([row('005930',100),row('005930',100)])),/중복/);
 assert.throws(()=>validatePassive({...data([]),meta:{data_kind:'example',unit:'KRW'}}),/실제/);
 assert.equal(validatePassive(data([row('005930',0)] )).stocks[0].net,0);
});
test('ETF ranking separates buying and selling, filters entities, and never ranks N/A as zero',()=>{
 const rows=[row('005930',100),row('000660',-200),row('018260',null,{adv_pct:null})];
 assert.deepEqual(passiveRanking(rows,'buy').map(r=>r.code),['005930']);
 assert.deepEqual(passiveRanking(rows,'sell').map(r=>r.code),['000660']);
 assert.equal(passiveRanking(rows,'buy','018260').length,0);
 assert.equal(passiveMoney(null),'N/A');assert.equal(passiveMoney(100000000),'1.0');
});
test('ETF history preserves missing observations rather than inventing daily zeros',()=>{
 const days=[{meta:{as_of:'2026-10-28'},stocks:[]},{meta:{as_of:'2026-10-29'},stocks:[{code:'005930',net:0}]}];
 const result=historyWindow(days,'005930',20);assert.equal(result[0].net,undefined);assert.equal(result[1].net,0);
});
