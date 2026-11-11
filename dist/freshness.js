export function healthMessage(h){
 if(!h?.checked_at)return '수집 상태 진단 미확보 · 기준일을 확인하세요.';
 const age=Date.now()-Date.parse(h.checked_at),old=!Number.isFinite(age)||age>2*3600000;
 const checked=new Date(h.checked_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});
 return `수급 ${h.flow_as_of||'미확보'} / 가격 ${h.price_as_of||'미확보'} · ${h.message||'상태 미확보'}${h.status==='waiting_runner'&&Number.isFinite(h.queued_or_run_age_minutes)?' · 확인 당시 대기 '+h.queued_or_run_age_minutes+'분':''} · 상태 확인 ${checked} KST${old?' · 진단도 오래됨: 현재 연결 상태 재확인 필요':''}`;
}
export async function mountFreshness(){
 const anchor=document.getElementById('notice');if(!anchor)return;
 const panel=document.createElement('p');panel.className='notice';panel.setAttribute('role','status');anchor.before(panel);
 try{const r=await fetch('data/refresh-health.json',{cache:'no-store'});if(!r.ok)throw Error();const h=await r.json();panel.textContent=healthMessage(h);
  if(typeof h.run_url==='string'&&/^https:\/\/github\.com\/fort4dream17-cloud\/-\/actions\/runs\/\d+$/.test(h.run_url)){const a=document.createElement('a');a.href=h.run_url;a.textContent=' 실행 상태 보기 ↗';a.target='_blank';a.rel='noopener noreferrer';panel.append(a);}
 }catch{panel.textContent='실행기 상태 진단 미확보 · 수급/가격 기준일을 확인하세요.';}
}
