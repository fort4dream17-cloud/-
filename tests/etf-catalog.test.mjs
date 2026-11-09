import test from 'node:test';import assert from 'node:assert/strict';
import {catalogRows,filterCatalog,holdingRows,reverseHoldings} from '../dist/etf-catalog.js';
test('current ETF catalog stays visible without monitor or holdings; duplicate/date conflicts excluded',()=>{
 const api={meta:{as_of:'2026-11-06'},funds:[{code:'069500',name:'KODEX 200',quote_date:'2026-11-06',turnover:1},{code:'069500',quote_date:'2026-11-06'},{code:'102110',quote_date:'2026-11-05'}]};
 assert.equal(catalogRows(api,null).length,1);assert.equal(catalogRows(api,{meta:{as_of:'2026-11-05'},funds:[{code:'069500',turnover:999} ]})[0].turnover,1);
});
test('catalog search covers codes and index; missing metrics sort after observed zero',()=>{
 const rows=[{code:'A',name:'Alpha',index:'KOSPI',turnover:null},{code:'B',name:'Beta',index:'KOSDAQ',turnover:0},{code:'C',name:'Gamma',index:'KOSPI',turnover:10}];
 assert.deepEqual(filterCatalog(rows,'','turnover').map(f=>f.code),['C','B','A']);assert.equal(filterCatalog(rows,'kosdaq').length,1);assert.equal(filterCatalog(rows,'B').length,1);
 assert.equal(filterCatalog(rows,'','turnover',true,{B:{}}).length,1);
});
test('holdings lookup distinguishes unavailable, dated and same-day; reverse lookup is only connected coverage',()=>{
 const h={funds:{'069500':{as_of:'2026-11-06',holdings:[{code:'005930'}]}},stocks:{'005930':{name:'삼성전자',etfs:[{etf_code:'069500'}]}}};
 assert.equal(holdingRows('102110',h,'2026-11-06').status,'unavailable');assert.equal(holdingRows('069500',h,'2026-11-09').status,'dated');assert.equal(holdingRows('069500',h,'2026-11-06').status,'current');assert.equal(reverseHoldings(h,'삼성')[0].code,'005930');assert.deepEqual(reverseHoldings(h,''),[]);
});
