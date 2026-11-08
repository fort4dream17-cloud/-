import test from 'node:test';
import assert from 'node:assert/strict';
import {priceHistoryRows} from '../dist/presentation.js';

test('new API closes extend the chart without extending investor flow observations',()=>{
 const m={last:{code:'005930',date:'2026-11-05',close:100},rows:[{code:'005930',date:'2026-11-05',close:100,pension:12,foreign:5}]};
 const h={meta:{as_of:'2026-11-06',price_basis:'raw'},stocks:{'005930':[['2026-11-05',100,10],['2026-11-06',110,20]]},benchmarks:[['2026-11-05',1000],['2026-11-06',1010]]};
 const rows=priceHistoryRows(m,h);
 assert.equal(rows.at(-1).date,'2026-11-06');assert.equal(rows.at(-1).close,110);
 assert.equal(rows.at(-1).pension,undefined);assert.equal(rows[0].pension,12);
 assert.equal(m.last.date,'2026-11-05');assert.equal(m.rows.length,1);
});
