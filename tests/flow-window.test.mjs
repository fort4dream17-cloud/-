import test from 'node:test';
import assert from 'node:assert/strict';
import {observedFlowWindow} from '../dist/presentation.js';
test('latest observed flow dates override stale window metadata without changing flow values',()=>{
 const dates=Array.from({length:60},(_,i)=>new Date(Date.UTC(2026,8,15+i)).toISOString().slice(0,10));
 const data={meta:{as_of:dates.at(-1),window_dates:{60:{from:'2026-07-31',to:'2026-10-29'}}},rows:dates.flatMap(date=>[{date,code:'005930',foreign:1},{date,code:'000660',foreign:2}])};
 assert.deepEqual(observedFlowWindow(data),{from:dates[0],to:dates.at(-1),sessions:60,complete:true});
 assert.equal(data.rows.reduce((n,r)=>n+r.foreign,0),180);
});
test('short history is explicit and later price-only dates are excluded',()=>{
 const d={meta:{as_of:'2026-11-13'},rows:[{date:'2026-11-12'},{date:'2026-11-13'},{date:'2026-11-16'}]};
 assert.deepEqual(observedFlowWindow(d),{from:'2026-11-12',to:'2026-11-13',sessions:2,complete:false});
});
