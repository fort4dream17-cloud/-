import {finite,price} from './engine.js';
// Legacy source JSON remains KRW_100M; every displayed/exported money value is KRW_1B.
export const billions=value=>finite(value)?value/10:null;
export function longFlowRanking(items,actor,side,metric='cap'){
 if(!['foreign','pension'].includes(actor)||!['buy','sell'].includes(side)||!['amount','cap','turnover'].includes(metric))throw Error('60일 랭킹 기준 오류');
 return items.filter(m=>{let w=m.actors[actor][60];return finite(w.amount)&&finite(w[metric])&&(side==='buy'?w.amount>0:w.amount<0)}).sort((a,b)=>{let d=(a.actors[actor][60][metric]-b.actors[actor][60][metric])*(side==='buy'?-1:1);return d||a.last.code.localeCompare(b.last.code)});
}
export function verifiedDisclosure(records,code,cutoff){
 return records.filter(r=>r.code===code&&r.verification==='opendart_api'&&r.ratio_type==='stock_etc_reported'&&/^\d{8}$/.test(r.corp_code||'')&&['국민연금공단','국민연금관리공단'].includes(r.reporter)&&finite(r.ownership_pct)&&r.ownership_pct>=0&&r.ownership_pct<=100&&/^\d{4}-\d{2}-\d{2}$/.test(r.published_at||'')&&r.published_at<=cutoff&&/^\d{14}$/.test(r.rcept_no||'')&&r.rcept_no.slice(0,8)===r.published_at.replaceAll('-','')&&r.source_url==='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+r.rcept_no).sort((a,b)=>b.published_at.localeCompare(a.published_at)||b.rcept_no.localeCompare(a.rcept_no))[0]||null;
}
export function priceHistoryRows(m,history){
 if(history?.meta?.as_of!==m.last.date||history.meta.price_basis!=='raw'||!Array.isArray(history.stocks?.[m.last.code])||!Array.isArray(history.benchmarks))return m.rows;
 const tuples=history.stocks[m.last.code],bench=new Map(history.benchmarks),observed=new Map(m.rows.map(r=>[r.date,r]));
 let seen=new Set(),lastDate='';
 for(const q of tuples){if(!Array.isArray(q)||q.length!==3||typeof q[0]!=='string'||q[0]<=lastDate||q[0]>m.last.date||(q[1]!==null&&(!finite(q[1])||q[1]<=0))||(q[2]!==null&&(!finite(q[2])||q[2]<0)))return m.rows;lastDate=q[0];seen.add(q[0]);}
 if(!tuples.length||tuples.at(-1)[0]!==m.last.date||tuples.at(-1)[1]!==m.last.close)return m.rows;
 // Provider disagreement in the overlapping window invalidates the extra history.
 if(m.rows.some(r=>!seen.has(r.date)||tuples.find(q=>q[0]===r.date)?.[1]!==r.close))return m.rows;
 let first=tuples.findIndex(q=>finite(q[1]));if(first<0)return m.rows;
 return tuples.slice(first).map(([date,close,volume])=>({date,close,volume,benchmark:bench.get(date)??null,...observed.get(date)}));
}
