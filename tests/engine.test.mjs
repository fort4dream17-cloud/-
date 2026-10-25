import test from 'node:test';import assert from 'node:assert/strict';
import {ACTORS,relative,ratio,actorMetrics,analyze,cumulative,movingAverage,validateDataset,parseCSV,rank,selectChartRows} from '../dist/engine.js';
function rows(n=80){return Array.from({length:n},(_,i)=>({date:new Date(Date.UTC(2025,0,i+1)).toISOString().slice(0,10),code:'042660',name:'한화오션',sector:'조선',close:100+i,adjusted_close:100+i,benchmark:100+i,marketcap:10000,turnover:100,volume:1000,foreign_ownership:10+i*.01,...Object.fromEntries(Object.keys(ACTORS).map(k=>[k,1]))}))}
function dataset(a=rows()){return{schema_version:2,meta:{data_kind:'real',status:'final',source:'unit-test fixture',unit:'KRW_100M',benchmark_name:'KOSPI fixture',price_basis:'adjusted',dividend_adjusted:false,fetched_at:'2025-05-01T00:00:00Z',as_of:a.at(-1).date,trading_dates:a.map(r=>r.date)},rows:a}}
test('geometric relative return; not arithmetic percentage-point difference',()=>{assert.ok(Math.abs(relative(100,110,100,105)-4.7619047619)<1e-8);assert.equal(relative(100,90,100,90),0);assert.equal(relative(0,90,100,90),null)});
test('all accumulation windows and two distinct normalization denominators',()=>{let a=rows(),m=actorMetrics(a,'pension');assert.equal(m[5].amount,5);assert.equal(m[10].amount,10);assert.equal(m[20].amount,20);assert.equal(m[60].amount,60);assert.equal(m[20].cap,.2);assert.equal(m[20].turnover,1);assert.equal(m.buyDays,20);assert.equal(m.streak,80);assert.equal(m.acceleration,0)});
test('minimum history, missing values and zero denominator are not zero-filled',()=>{assert.equal(actorMetrics(rows(4),'pension')[5].amount,null);let a=rows();a.at(-3).pension=null;assert.equal(actorMetrics(a,'pension')[5].amount,null);assert.equal(ratio(1,0),null);assert.equal(analyze(rows(20)).rel20,null);assert.ok(Math.abs(analyze(rows()).ownershipChange-.2)<1e-10)});
test('A uses previous disjoint 20 days and minimum five-day buy count',()=>{let a=rows(25);a.forEach((r,i)=>r.pension=i<20?-10:20);assert.ok(analyze(a).signals.includes('A'));assert.ok(!analyze(a,{minBuyDays:5,minAmount:101}).signals.includes('A'));a.slice(-4).forEach(r=>r.pension=0);assert.ok(!analyze(a).signals.includes('A'))});
test('foreign new accumulation and foreign acceleration distinct',()=>{let a=rows();a.forEach((r,i)=>r.foreign=i<75?-10:20);let m=analyze(a);assert.ok(m.signals.includes('FN'));assert.ok(m.signals.includes('D'));assert.equal(m.actors.foreign.acceleration,30)});
test('B requires both positive five- and twenty-day windows',()=>{let a=rows();assert.ok(analyze(a).signals.includes('B'));a.slice(-20,-5).forEach(r=>r.foreign=-100);assert.ok(!analyze(a).signals.includes('B'))});
test('C accepts foreign accumulation even if pension sells',()=>{let a=rows();a.forEach((r,i)=>{r.adjusted_close=100-i*.1;r.pension=-1});assert.ok(analyze(a).signals.includes('C'));assert.ok(!analyze(a,{divergence:100}).signals.includes('C'))});
test('E detects disjoint reversal and simultaneous selling',()=>{let a=rows();a.slice(-5).forEach(r=>{r.pension=-10;r.foreign=-10});assert.ok(analyze(a).signals.includes('E'));assert.equal(actorMetrics(a,'pension').streak,-5)});
test('F requires a verified event AND abnormal volume; no arbitrary passive claim',()=>{let a=rows();a.at(-1).volume=5000;assert.equal(analyze(a).passive,'미확인');a.at(-1).events=[{type:'index_change',verified:false,source_url:'https://example.com'}];assert.ok(!analyze(a).signals.includes('F'));a.at(-1).events[0].verified=true;assert.ok(analyze(a).signals.includes('F'));assert.ok(!analyze(a,{passiveVolume:6}).signals.includes('F'))});
test('cumulative chart begins zero and preserves a missing-data break',()=>{let a=rows(5);assert.deepEqual(cumulative(a,'pension'),[0,1,2,3,4]);a[2].pension=null;assert.deepEqual(cumulative(a,'pension'),[0,1,null,null,null]);assert.deepEqual(movingAverage(rows(3),2),[null,100.5,101.5])});
test('duplicate, missing trading date and inconsistent benchmark rejected',()=>{let d=dataset();assert.equal(validateDataset(d).groups.length,1);assert.throws(()=>validateDataset({...d,rows:[...d.rows,d.rows[0]]}),/중복/);assert.throws(()=>validateDataset({...d,rows:d.rows.filter((r,i)=>i!==40)}),/거래일 누락/);let other=d.rows.map(r=>({...r,code:'010140',benchmark:r.benchmark+1}));assert.throws(()=>validateDataset({...d,rows:[...d.rows,...other]}),/지수가 다릅니다/)});
test('schema unit and adjusted price enforced; missing actors remain null',()=>{let d=dataset();assert.throws(()=>validateDataset({...d,meta:{...d.meta,unit:'KRW'}}),/금액 단위/);delete d.rows[0].adjusted_close;assert.throws(()=>validateDataset(d),/수정종가/);let a=rows();delete a.at(-1).pension;assert.equal(analyze(a).actors.pension[5].amount,null)});
test('CSV supports BOM, quoted commas and empty cells, rejects malformed rows',()=>{assert.deepEqual(parseCSV('\ufeffdate,code,name,pension\n2025-01-01,042660,"한화,오션",\n')[0],{date:'2025-01-01',code:'042660',name:'한화,오션',pension:null});assert.throws(()=>parseCSV('a,b\n1,2,3'),/열 개수/)});
test('scores bounded, tied universe neutral, missing factors withheld',()=>{let a=[0,1,2,3].map(j=>analyze(rows().map(r=>({...r,code:'00000'+j,pension:j+1,foreign:j*2}))));let ranked=rank(a);assert.ok(ranked.every(m=>m.score>=0&&m.score<=100));assert.equal(rank([a[0],a[1]])[0].score,null);let ties=rank([a[0],a[0],a[0]]);assert.ok(ties.every(m=>m.score===50));assert.ok(rank(a).at(-1).score>rank(a)[0].score)});

test('calendar ranges include prior year closing baseline for YTD',()=>{
 const a=['2025-12-29','2025-12-30','2026-01-02','2026-03-31','2026-06-30','2026-09-30'].map(date=>({date}));
 assert.equal(selectChartRows(a,'YTD').rows[0].date,'2025-12-30');
 assert.equal(selectChartRows(a,'YTD').complete,true);
 assert.equal(selectChartRows(a,'3M').requestedStart,'2026-06-30');
 assert.equal(selectChartRows(a,'3M').rows[0].date,'2026-06-30');
 assert.equal(selectChartRows(a,'6M').requestedStart,'2026-03-30');
 assert.equal(selectChartRows(a,'1Y').complete,false);
 assert.equal(selectChartRows(a.slice(-2),'YTD').complete,false);
 assert.equal(selectChartRows(a,'5').rows.length,5);
});
test('calendar month arithmetic clamps leap days and keeps insufficient history explicit',()=>{
 assert.equal(selectChartRows([{date:'2024-02-29'}],'1Y').requestedStart,'2023-02-28');
 assert.deepEqual(selectChartRows([],'YTD').rows,[]);
 assert.throws(()=>selectChartRows([{date:'2024-02-29'}],'BAD'));
 const a=rows(65);a.forEach(r=>r.sector='반도체');assert.equal(validateDataset(dataset(a)).groups.length,1);
 a[0].sector='';assert.throws(()=>validateDataset(dataset(a)));
});
