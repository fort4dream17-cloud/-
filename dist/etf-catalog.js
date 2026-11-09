const finite=v=>typeof v==='number'&&Number.isFinite(v);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>finite(v)?(v/1e8).toLocaleString('ko-KR',{maximumFractionDigits:1}):'N/A';
const number=v=>finite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:2}):'N/A';
const pct=v=>finite(v)?(v>0?'+':'')+v.toFixed(2)+'%':'N/A';
const cls=v=>finite(v)?v>0?'pos':v<0?'neg':'':'';
export function catalogRows(api,monitor){
 const asof=api?.meta?.as_of;if(!asof||!Array.isArray(api.funds))return [];
 const metrics=new Map(monitor?.meta?.as_of===asof?(monitor.funds||[]).map(f=>[f.code,f]):[]);const seen=new Set();
 return api.funds.filter(f=>{if(!/^[0-9A-Z]{6}$/.test(f.code)||seen.has(f.code)||f.quote_date!==asof)return false;seen.add(f.code);return true;}).map(f=>({...f,...metrics.get(f.code)}));
}
export function filterCatalog(rows,query='',sort='turnover',onlyHoldings=false,holdings={}){
 const q=query.trim().toLocaleLowerCase();return rows.filter(f=>(!q||[f.code,f.name,f.index,f.manager].some(v=>String(v??'').toLocaleLowerCase().includes(q)))&&(!onlyHoldings||holdings[f.code])).sort((a,b)=>{
  if(sort==='name')return a.name.localeCompare(b.name,'ko');const av=a[sort],bv=b[sort];return finite(av)&&finite(bv)?bv-av||a.code.localeCompare(b.code):finite(av)?-1:finite(bv)?1:a.code.localeCompare(b.code);
 });
}
export function holdingRows(code,holdings,quoteDate){
 const f=holdings?.funds?.[code];if(!f)return {status:'unavailable',rows:[]};
 return {status:f.as_of===quoteDate?'current':'dated',as_of:f.as_of,source_url:f.source_url,rows:f.holdings||[],basis:f.quantity_basis};
}
export function reverseHoldings(holdings,query){
 const q=query.trim().toLocaleLowerCase();if(!q)return [];
 return Object.entries(holdings?.stocks||{}).filter(([c,s])=>c.includes(q)||s.name.toLocaleLowerCase().includes(q)).slice(0,20).map(([code,s])=>({code,...s}));
}
export function mountEtfCatalog(root){
 let api=null,monitor=null,holdings=null,rows=[],page=0,selected=null,chart=null;
 root.innerHTML=`<div class="section-head"><div><h3>국내 ETF 전체 시세 · 구성종목 조회</h3><p class="muted">ETF 거래대금은 개별 주식 순매수가 아닙니다. 금액: 억원</p></div><button type="button" id="etfCatalogCsv">ETF 목록 CSV ↓</button></div>
 <p id="etfCatalogStatus" class="muted" role="status">ETF 시세 불러오는 중</p>
 <div class="toolbar"><input id="etfCatalogQuery" type="search" aria-label="ETF 이름 코드 지수 검색" placeholder="ETF명 / 코드 / 추종지수"><select id="etfCatalogSort" aria-label="ETF 정렬"><option value="turnover">거래대금 순</option><option value="aum">AUM 순</option><option value="turnover_rvol">거래대금 RVOL 순</option><option value="units_change_value">좌수변화 환산액 순</option><option value="name">이름 순</option></select><label><input type="checkbox" id="etfHoldingsOnly"> 구성종목 연결 ETF만</label></div>
 <div class="table-scroll etf-catalog-scroll" id="etfCatalog"></div><div class="toolbar"><span id="etfCatalogCount" class="muted"></span><span class="spacer"></span><button type="button" id="etfCatalogPrev">이전</button><button type="button" id="etfCatalogNext">다음</button></div>
 <article id="etfQuoteDetail" hidden><h3 id="etfQuoteName"></h3><div id="etfQuoteKpis" class="etf-kpis"></div><p class="muted" id="etfQuoteBasis"></p><div id="etfQuoteChart" class="etf-history-chart" role="img" aria-label="선택 ETF 실제 종가와 NAV"></div><details><summary>시세 일간 이력 표</summary><div class="table-scroll" id="etfQuoteHistory"></div></details><h4>편입 국내주식 · 운용사 공개 PDF</h4><p id="etfHoldingBasis" class="muted"></p><div class="table-scroll etf-holdings-scroll" id="etfHoldingTable"></div></article>
 <div class="section-head"><div><h3>주식 → 편입 ETF 역조회</h3><p class="muted">연결된 운용사 자료 안에서 조회합니다. 미연결 ETF는 해당 종목을 보유하지 않는다는 뜻이 아닙니다.</p></div><input id="etfReverseQuery" type="search" aria-label="주식 편입 ETF 검색" placeholder="예: 삼성전자 / 005930"></div><div id="etfReverseResults" class="table-scroll">주식명 또는 코드를 입력하세요.</div>`;
 const $=id=>root.querySelector('#'+id);
 function table(list){return `<table class="etf-rank-table"><thead><tr><th>ETF / 코드</th><th>기준일</th><th>종가 원</th><th>등락률</th><th>AUM 억원</th><th>거래대금 억원</th><th>거래대금 RVOL</th><th>NAV 괴리</th><th>좌수변화 환산액<br>억원 · 미검증</th><th>구성종목</th></tr></thead><tbody>${list.map(f=>{const h=holdings?.funds?.[f.code];return `<tr data-etf-quote="${f.code}" tabindex="0" role="button" aria-label="${esc(f.name)} 시세 구성종목"><td><b>${esc(f.name)}</b><small>${f.code} · ${esc(f.index||'지수 미확보')}</small></td><td>${esc(f.quote_date)}</td><td>${number(f.close)}</td><td class="${cls(f.return_pct)}">${pct(f.return_pct)}</td><td>${money(f.aum)}</td><td>${money(f.turnover)}</td><td>${finite(f.turnover_rvol)?f.turnover_rvol.toFixed(2)+'×':'N/A'}</td><td class="${cls(f.nav_gap_pct)}">${pct(f.nav_gap_pct)}</td><td class="${cls(f.units_change_value)}">${money(f.units_change_value)}</td><td>${h?(h.as_of===f.quote_date?'연결':'다른 기준일')+' · '+h.domestic_stock_count+'종목':'미연결'}</td></tr>`;}).join('')||'<tr><td colspan="10">조건에 맞는 ETF가 없습니다.</td></tr>'}</tbody></table>`;}
 function render(){
  const list=filterCatalog(rows,$('etfCatalogQuery').value,$('etfCatalogSort').value,$('etfHoldingsOnly').checked,holdings?.funds||{});const pages=Math.max(1,Math.ceil(list.length/50));page=Math.min(page,pages-1);
  $('etfCatalog').innerHTML=table(list.slice(page*50,page*50+50));$('etfCatalogCount').textContent=`${list.length.toLocaleString()}개 / 전체 ${rows.length.toLocaleString()}개 · ${page+1} / ${pages}페이지`;$('etfCatalogPrev').disabled=page===0;$('etfCatalogNext').disabled=page>=pages-1;$('etfCatalogCsv').disabled=!list.length;
  const hm=holdings?.meta;const count=rows.filter(f=>holdings?.funds?.[f.code]?.as_of===f.quote_date).length;
  $('etfCatalogStatus').textContent=rows.length?`시세 기준 ${api.meta.as_of} · 출처 KRX OpenAPI · 갱신 ${api.meta.fetched_at||'미확보'} · 동일 날짜 구성종목 ${count} / ${rows.length}개 (${(count/rows.length*100).toFixed(1)}%) · ${hm?.scope||'운용사 구성종목 수집 대기'}${hm?.source_rate_limited?' · 운용사 요청 제한(429): 자동 조회 일시 중지 · 재시도 가능 '+hm.retry_after:hm?.status==='failed'?' · 최근 구성종목 수집 실패: 보존된 자료의 기준일 확인':''}`:'ETF 시세 자료 미확보 · N/A';
 }
 function select(code){
  const f=rows.find(x=>x.code===code);if(!f)return;selected=code;$('etfQuoteDetail').hidden=false;$('etfQuoteName').textContent=f.name+' · '+code;
  $('etfQuoteKpis').innerHTML=[['종가 · 원',number(f.close)],['NAV · 원',number(f.nav)],['AUM · 억원',money(f.aum)],['발행좌수',number(f.units)],['거래량',number(f.volume)],['거래량 RVOL',finite(f.volume_rvol)?f.volume_rvol.toFixed(2)+'×':'N/A'],['5일 수익률',pct(f.returns?.['5'])],['20일 수익률',pct(f.returns?.['20'])],['60일 수익률',pct(f.returns?.['60'])]].map(([k,v])=>`<div><span>${k}</span><strong>${v}</strong></div>`).join('');
  $('etfQuoteBasis').textContent=`${f.quote_date} · 비수정 종가·배당 미반영. 좌수변화 환산액은 (당일−직전 관측일 좌수)×당일 NAV이며 분할·합병 미검증으로 설정·환매 확정액 및 개별 주식 매매액이 아닙니다.`;
  const points=monitor?.meta?.as_of===f.quote_date?(monitor.history?.[code]||[]).filter(p=>p[0]<=f.quote_date):[];
  $('etfQuoteHistory').innerHTML=`<table><thead><tr><th>날짜</th><th>종가 원</th><th>NAV 원</th><th>AUM 억원</th><th>발행좌수</th><th>거래대금 억원</th></tr></thead><tbody>${[...points].reverse().map(p=>`<tr><td>${esc(p[0])}</td><td>${number(p[1])}</td><td>${number(p[2])}</td><td>${money(p[3])}</td><td>${number(p[4])}</td><td>${money(p[5])}</td></tr>`).join('')}</tbody></table>`;
  if(points.length&&window.echarts){$('etfQuoteChart').textContent='';chart??=window.echarts.init($('etfQuoteChart'));chart.setOption({animation:false,tooltip:{trigger:'axis',confine:true},legend:{data:['종가','NAV']},grid:{top:40,left:70,right:25,bottom:40},xAxis:{type:'category',data:points.map(p=>p[0])},yAxis:{type:'value',scale:true},series:[{name:'종가',type:'line',data:points.map(p=>p[1]),connectNulls:false,showSymbol:false},{name:'NAV',type:'line',data:points.map(p=>p[2]),connectNulls:false,showSymbol:false}]},true);chart.resize();}else{chart?.dispose();chart=null;$('etfQuoteChart').textContent='시세 이력 N/A · 표에서 확보된 자료를 확인하세요.';}
  const h=holdingRows(code,holdings,f.quote_date);const source=typeof h.source_url==='string'&&h.source_url.startsWith('https://www.samsungfund.com/etf/product/view.do?id=')?` <a href="${esc(h.source_url)}" target="_blank" rel="noopener noreferrer">운용사 원자료 ↗</a>`:'';
  $('etfHoldingBasis').innerHTML=h.status==='unavailable'?'구성종목 미연결 · 시세 수집과 별도입니다. 미편입 또는 보유량 0을 의미하지 않습니다.':`${esc(h.as_of)} · ${esc(h.basis)} · ${h.status==='dated'?'시세와 기준일이 달라 영향 추정 보류 · ':''}현금·선물·해외자산·ETF 재간접 구성은 아래 국내주식 목록에서 제외합니다.${source}`;
  $('etfHoldingTable').innerHTML=h.rows.length?`<table><thead><tr><th>국내주식 / 코드</th><th>PDF 비중 %</th><th>PDF 구성수량</th><th>AUM×비중 억원<br>노출 근사치</th></tr></thead><tbody>${h.rows.map(r=>`<tr><td>${esc(r.name)} <small>${r.code}</small></td><td>${finite(r.weight_pct)?r.weight_pct.toFixed(2):'N/A'}</td><td>${number(r.pdf_quantity)}</td><td>${h.status==='current'&&finite(r.weight_pct)&&finite(f.aum)?money(f.aum*r.weight_pct/100):'N/A'}</td></tr>`).join('')}</tbody></table>`:'N/A · 연결된 국내주식 구성자료 없음';
 }
 function reverse(){
  const matches=reverseHoldings(holdings,$('etfReverseQuery').value);$('etfReverseResults').innerHTML=matches.length?matches.map(s=>`<h4>${esc(s.name)} · ${s.code} · 연결 범위 ${s.etfs.length}개 ETF</h4><table><thead><tr><th>ETF</th><th>PDF 기준일</th><th>PDF 비중 %</th><th>노출 근사치 억원</th></tr></thead><tbody>${s.etfs.map(e=>{const f=rows.find(r=>r.code===e.etf_code);return `<tr data-etf-quote="${e.etf_code}" tabindex="0"><td>${esc(f?.name||e.etf_code)}</td><td>${esc(e.as_of)}</td><td>${finite(e.weight_pct)?e.weight_pct.toFixed(2):'N/A'}</td><td>${f&&e.as_of===f.quote_date&&finite(e.weight_pct)&&finite(f.aum)?money(f.aum*e.weight_pct/100):'N/A'}</td></tr>`;}).join('')}</tbody></table>`).join(''):$('etfReverseQuery').value.trim()?'연결된 운용사 범위에서 검색 결과 없음 · 다른 운용사 미수집 ETF는 포함되지 않습니다.':'주식명 또는 코드를 입력하세요.';
 }
 for(const id of ['etfCatalogQuery','etfCatalogSort','etfHoldingsOnly'])$(id).addEventListener(id==='etfCatalogQuery'?'input':'change',()=>{page=0;render();});
 $('etfCatalogPrev').onclick=()=>{page--;render();};$('etfCatalogNext').onclick=()=>{page++;render();};$('etfReverseQuery').oninput=reverse;
 root.addEventListener('click',e=>{const el=e.target.closest('[data-etf-quote]');if(el)select(el.dataset.etfQuote);});root.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.etfQuote)select(e.target.dataset.etfQuote);});
 $('etfCatalogCsv').onclick=()=>{const list=filterCatalog(rows,$('etfCatalogQuery').value,$('etfCatalogSort').value,$('etfHoldingsOnly').checked,holdings?.funds||{});const quote=v=>'"'+String(v??'N/A').replaceAll('"','""')+'"';const csv='\ufeff'+[['ETF코드','ETF명','기준일','종가_원','AUM_억원','거래대금_억원','거래대금_RVOL','NAV괴리_%','좌수변화환산액_억원_미검증'],...list.map(f=>[f.code,f.name,f.quote_date,f.close,finite(f.aum)?f.aum/1e8:null,finite(f.turnover)?f.turnover/1e8:null,f.turnover_rvol,f.nav_gap_pct,finite(f.units_change_value)?f.units_change_value/1e8:null])].map(r=>r.map(quote).join(',')).join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='ETF_market_'+api.meta.as_of+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 new ResizeObserver(()=>chart?.resize()).observe($('etfQuoteChart'));
 return {update(a,m,h){api=a;monitor=m;holdings=h;rows=catalogRows(a,m);render();reverse();if(selected)select(selected);}};
}
