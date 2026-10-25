import test from 'node:test';
import assert from 'node:assert/strict';
import {billions,longFlowRanking,flowRegime,verifiedDisclosure,priceHistoryRows} from '../dist/presentation.js';
import {movingAverage} from '../dist/engine.js';
test('display money scales once and missing values remain missing',()=>{
 assert.equal(billions(1000),100);assert.equal(billions(-12.5),-1.25);assert.equal(billions(null),null);
});
test('60-session buyers and sellers are separate and can rank by absolute or relative flow',()=>{
 const make=(code,amount,cap)=>({last:{code},actors:{foreign:{60:{amount,cap,turnover:cap*2}}}});
 const items=[make('000001',100,1),make('000002',50,2),make('000003',-200,-3),make('000004',null,null),make('000005',0,0)];
 assert.deepEqual(longFlowRanking(items,'foreign','buy','cap').map(m=>m.last.code),['000002','000001']);
 assert.deepEqual(longFlowRanking(items,'foreign','buy','amount').map(m=>m.last.code),['000001','000002']);
 assert.deepEqual(longFlowRanking(items,'foreign','sell').map(m=>m.last.code),['000003']);
});
test('unverified, future and mismatched receipt records cannot become NPS ownership',()=>{
 const r={code:'329180',corp_code:'01390344',reporter:'국민연금공단',ownership_pct:8.02,published_at:'2026-09-08',rcept_no:'20260908000302',source_url:'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260908000302',verification:'opendart_api',ratio_type:'stock_etc_reported'};
 assert.equal(verifiedDisclosure([r],r.code,'2026-10-23'),r);
 for(const v of [{...r,verification:undefined},{...r,reporter:'다른 주주'},{...r,rcept_no:'20260909000302'},{...r,ownership_pct:101}])assert.equal(verifiedDisclosure([v],r.code,'2026-10-23'),null);
 assert.equal(verifiedDisclosure([r],r.code,'2026-09-01'),null);
});
test('long price history never overwrites flow observations and rejects provider conflicts',()=>{
 const m={last:{code:'000001',date:'2026-10-23',close:110},rows:[{date:'2026-10-22',close:100,pension:2},{date:'2026-10-23',close:110,pension:3}]};
 const h={meta:{as_of:'2026-10-23',price_basis:'raw'},benchmarks:[['2026-10-21',90],['2026-10-22',100],['2026-10-23',105]],stocks:{'000001':[['2026-10-21',90,10],['2026-10-22',100,11],['2026-10-23',110,12]]}};
 const rows=priceHistoryRows(m,h);assert.equal(rows.length,3);assert.equal(rows[0].pension,undefined);assert.equal(rows[2].pension,3);
 h.stocks['000001'][1][1]=999;assert.equal(priceHistoryRows(m,h),m.rows);
});
test('moving average needs valid contiguous sessions and uses warm-up observations',()=>{
 let rows=Array.from({length:80},(_,i)=>({close:i+1}));assert.equal(movingAverage(rows,60)[59],30.5);assert.equal(movingAverage(rows,60).at(-1),50.5);
 rows[70].close=null;assert.equal(movingAverage(rows,60).at(-1),null);
});

test('long and short flow regimes do not claim an unobserved turning date',()=>{assert.equal(flowRegime({60:{amount:10},5:{amount:-1}}),'누적 매수 속 단기 매도');assert.equal(flowRegime({60:{amount:-10},5:{amount:1}}),'누적 매도 속 단기 매수');assert.equal(flowRegime({60:{amount:null},5:{amount:1}}),'기간 비교 미확인')});

test('60-session rankings exclude a known short listing history',()=>{let m={last:{code:'0220W0'},flow60Sessions:41,actors:{foreign:{60:{amount:-100,cap:-10,turnover:-5}}}};assert.deepEqual(longFlowRanking([m],'foreign','sell'),[])});

test('reported ratios older than a year are not shown as current data',()=>{const r={code:'329180',corp_code:'01390344',reporter:'국민연금공단',ownership_pct:8.02,published_at:'2024-09-08',rcept_no:'20240908000302',source_url:'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240908000302',verification:'opendart_api',ratio_type:'stock_etc_reported'};assert.equal(verifiedDisclosure([r],r.code,'2026-10-23'),null)});
