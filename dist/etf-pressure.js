const ok=v=>typeof v==='number'&&Number.isFinite(v);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>ok(v)?(v/1e8).toLocaleString('ko-KR',{maximumFractionDigits:2}):'N/A';
const pct=v=>ok(v)?v.toFixed(2)+'%':'N/A';
export function estimatePressure(api,monitor,holdings,datasets=[],maxAge=7){
 const date=api?.meta?.as_of;if(!date)return {rows:[],excluded:[],used:0,total:0};
 const metrics=new Map((monitor?.meta?.as_of===date?monitor.funds:[]).map(f=>[f.code,f]));
 const groups=new Map(),seen=new Set();
 for(const d of datasets){if(d?.meta?.data_kind!=='real')continue;const scale={KRW_1B:1e9,KRW_100M:1e8}[d.meta.unit];if(!scale)continue;
  for(const r of d.rows||[]){const id=r.code+r.date;if(seen.has(id)||r.date>date)continue;seen.add(id);if(!groups.has(r.code))groups.set(r.code,[]);groups.get(r.code).push({...r,scale});}}
 const stocks=new Map(),excluded=[];let used=0;
 for(const [code,h] of Object.entries(holdings?.funds||{})){
  const f=metrics.get(code),age=(Date.parse(date)-Date.parse(h.as_of))/86400000,points=monitor?.history?.[code]||[],current=points.at(-1),previous=points.at(-2);
  let reason=null;
  if(/액티브|레버리지|인버스|합성/.test(h.name||f?.name||''))reason='액티브·파생형 별도 모형 필요';
  else if(!Number.isFinite(age)||age<0||age>maxAge)reason='편입비중 기준일 범위 초과';
  else if(!f||f.quote_date!==date||current?.[0]!==date||!previous||!ok(previous[4])||previous[4]<=0||!ok(f.units)||!ok(f.nav)||f.nav<=0)reason='좌수·NAV·직전 관측 미확보';
  else if(Math.abs(f.units/previous[4]-1)>0.2)reason='좌수 20% 초과 변동 · 기업행위 검증 필요';
  else if(!h.holdings?.length||h.holdings.some(r=>!ok(r.weight_pct)||r.weight_pct<0)||h.holdings.reduce((s,r)=>s+r.weight_pct,0)>101)reason='비중 미확보 또는 합계 검증 실패';
  if(reason){excluded.push({code,name:f?.name||h.name,reason});continue;}
  const codes=new Set();if(h.holdings.some(r=>codes.has(r.code)||!codes.add(r.code))){excluded.push({code,name:h.name,reason:'편입종목 중복'});continue;}
  used++;const flow=(f.units-previous[4])*f.nav;
  for(const r of h.holdings){if(!stocks.has(r.code))stocks.set(r.code,{code:r.code,name:r.name,net:0,buy:0,sell:0,etfs:[]});const s=stocks.get(r.code),effect=flow*r.weight_pct/100;s.net+=effect;s.buy+=Math.max(0,effect);s.sell+=Math.min(0,effect);s.etfs.push({code,name:f.name,as_of:h.as_of,age,weight:r.weight_pct,flow,effect});}
 }
 for(const s of stocks.values()){
  const rows=(groups.get(s.code)||[]).sort((a,b)=>a.date.localeCompare(b.date)),prior=rows.filter(r=>r.date<date).slice(-20),last=rows.find(r=>r.date===date);
  // Require exactly the market sessions used by the ETF signal, not 20 arbitrary old observations.
  const expected=Object.values(monitor?.history||{})[0]?.filter(p=>p[0]<date).slice(-20).map(p=>p[0])||[];
  s.adv=prior.length===20&&expected.length===20&&prior.every((r,i)=>r.date===expected[i]&&ok(r.turnover))?prior.reduce((v,r)=>v+r.turnover*r.scale,0)/20:null;
  s.advPct=ok(s.adv)&&s.adv>0?s.net/s.adv*100:null;
  s.financial=last&&ok(last.financial)&&s.adv>0?last.financial*last.scale/s.adv*100:null;
  s.foreign=last&&ok(last.foreign)&&s.adv>0?last.foreign*last.scale/s.adv*100:null;
  s.institution=last&&ok(last.institution)&&s.adv>0?last.institution*last.scale/s.adv*100:null;
  s.turnoverRatio=last&&ok(last.turnover)&&s.adv>0?last.turnover*last.scale/s.adv:null;
  s.etfs.sort((a,b)=>Math.abs(b.effect)-Math.abs(a.effect));s.confidence='낮음 · 비중 근사/기업행위 미검증';
 }
 return {date,rows:[...stocks.values()],excluded,used,total:api.funds.length,pdfCount:Object.keys(holdings?.funds||{}).length};
}
export function mountPressure(root){
 let inputs=null,result=null,selected=null;
 root.innerHTML=`<h3>종목별 ETF 추정 매매압력 · 연결 범위 내 부분 집계</h3><p>좌수 변화 × NAV × 공개 편입비중. 실제 체결액·확정 설정환매액이 아닙니다. 미수집 ETF의 반대 수요가 누락될 수 있습니다.</p><div class="toolbar"><input id="pressureSearch" type="search" aria-label="패시브 압력 종목 검색" placeholder="종목명 / 코드"><label>비중 최대 경과일 <select id="pressureAge"><option value="7">7일</option><option value="30">30일 · 신뢰도 낮음</option><option value="0">동일 기준일만</option></select></label><label>정렬 <select id="pressureSort"><option value="advPct">ADV20 대비</option><option value="net">추정 금액</option></select></label></div><p id="pressureState" class="notice"></p><div class="etf-rank-grid"><article><h3>매수 압력 상위 25</h3><div id="pressureBuy" class="table-scroll"></div></article><article><h3>매도 압력 상위 25</h3><div id="pressureSell" class="table-scroll"></div></article></div><div id="pressureDetail"></div><details><summary>계산 제외 ETF 및 제한사항</summary><div id="pressureExcluded"></div><p>리밸런싱 효과·5/20/60일 누적은 시점별 비중/기업행위 검증 이력 미확보로 N/A입니다. 과거를 현재 비중으로 소급 계산하지 않습니다. ADV20이 없는 종목은 금액 정렬에서 확인하세요. 거래대금은 신호일 이전 20거래일 기준이며 미확보는 N/A입니다. 20% 변동 제외 규칙은 이상치 필터이며 기업행위 검증을 대신하지 않습니다. 연결 ETF 수 비율은 해당 종목 노출액의 커버리지가 아닙니다.</p></details>`;
 const $=id=>root.querySelector('#'+id);
 function detail(code){selected=code;const r=result?.rows.find(r=>r.code===code);if(!r)return;$('pressureDetail').innerHTML=`<h3>${esc(r.name)} · 기여 ETF ${r.etfs.length}개</h3><p>추정 순압력 ${money(r.net)}억원 · 매수 합 ${money(r.buy)}억원 · 매도 합 ${money(r.sell)}억원 · ADV20 대비 ${pct(r.advPct)} · 금융투자 ${pct(r.financial)} / 외국인 ${pct(r.foreign)} / 기관계 ${pct(r.institution)} · 거래대금/ADV20 ${ok(r.turnoverRatio)?r.turnoverRatio.toFixed(2)+'×':'N/A'}</p><div class="table-scroll"><table><thead><tr><th>ETF</th><th>비중 기준일</th><th>비중 %</th><th>좌수변화 환산액 억원</th><th>종목 예상수요 억원</th></tr></thead><tbody>${r.etfs.map(e=>`<tr><td>${esc(e.name)} · ${e.code}</td><td>${esc(e.as_of)} · ${e.age}일 경과</td><td>${e.weight.toFixed(2)}</td><td>${money(e.flow)}</td><td>${money(e.effect)}</td></tr>`).join('')}</tbody></table></div><p>리밸런싱 N/A · 실제 체결 및 기업행위 미검증 · 전체 편입 ETF 목록이 아닌 연결 범위입니다.</p>`;}
 function render(){if(!inputs)return;result=estimatePressure(...inputs,Number($('pressureAge').value));const q=$('pressureSearch').value.trim(),key=$('pressureSort').value;
 $('pressureState').textContent=`기준 ${result.date||'N/A'} · 계산 ETF ${result.used} / 전체 ${result.total} · 확보 PDF ${result.pdfCount} · 계산 종목 ${result.rows.length} · 신뢰도 낮음 · 전체 ETF 압력 아님`;
 for(const [id,sign] of [['pressureBuy',1],['pressureSell',-1]]){const rows=result.rows.filter(r=>(r.name.includes(q)||r.code.includes(q))&&ok(r[key])&&r.net*sign>0).sort((a,b)=>sign*(b[key]-a[key])).slice(0,25);$(id).innerHTML=`<table><thead><tr><th>종목</th><th>순압력 억원</th><th>ADV20 %</th><th>매수/매도 억원</th><th>주요 ETF / 신뢰도</th></tr></thead><tbody>${rows.map(r=>`<tr><td><button data-pressure-code="${r.code}">${esc(r.name)}</button><small>${r.code}</small></td><td class="${r.net>0?'pos':'neg'}">${money(r.net)}</td><td>${pct(r.advPct)}</td><td>${money(r.buy)} / ${money(r.sell)}</td><td>${esc(r.etfs[0]?.name)}<small>${esc(r.confidence)}</small></td></tr>`).join('')||'<tr><td colspan="5">계산 가능한 해당 방향 종목 없음 · 금액 정렬 및 누락 범위 확인</td></tr>'}</tbody></table>`;}
 $('pressureExcluded').textContent=result.excluded.map(e=>`${e.name||e.code}: ${e.reason}`).join(' / ')||'연결 자료 중 제외 없음 · 미연결 ETF는 계산에 포함되지 않음';if(selected)detail(selected);
 }
 root.addEventListener('click',e=>{const b=e.target.closest('[data-pressure-code]');if(b)detail(b.dataset.pressureCode);});$('pressureSearch').oninput=render;$('pressureAge').onchange=render;$('pressureSort').onchange=render;
 return {update(...args){inputs=args;render();}};
}
