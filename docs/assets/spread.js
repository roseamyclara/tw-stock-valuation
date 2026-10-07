(() => {
'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const getJSON=async u=>{const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw new Error(u+' '+r.status);return r.json()};
const median=a=>{const x=a.filter(Number.isFinite).sort((a,b)=>a-b);if(!x.length)return null;const m=Math.floor(x.length/2);return x.length%2?x[m]:(x[m-1]+x[m])/2};
const weightedMedian=(vals,weights)=>{const a=vals.map((v,i)=>[v,weights[i]]).filter(x=>Number.isFinite(x[0])&&x[1]>0).sort((a,b)=>a[0]-b[0]);if(!a.length)return null;const total=a.reduce((s,x)=>s+x[1],0);let c=0;for(const x of a){c+=x[1];if(c>=total/2)return x[0]}return a[a.length-1][0]};
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const fmtPct=v=>v==null?'—':(v>0?'+':'')+v.toFixed(1)+'%';
const fmtRel=v=>v==null?'—':v.toFixed(2);
const cls=v=>v==null?'':v<-.05?'spread-neg':v>.05?'spread-pos':'spread-zero';
const finVal=(r,k)=>r&&r.fin&&Number.isFinite(r.fin[k])?r.fin[k]:null;
const twGrowth=r=>finVal(r,'rev_yoy') ?? (r.rev&&Number.isFinite(r.rev.yoy)?r.rev.yoy:null) ?? (r.rev&&Number.isFinite(r.rev.cum_yoy)?r.rev.cum_yoy:null);
const usGrowth=r=>finVal(r,'rev_yoy');
const ADR_EXCLUDE=new Set(['TSM','UMC','ASX','AUO','HIMX']);

function classifyTw(r,tags){
  const s=[r.i||'',...(tags[r.c]||[])].join('|').toLowerCase(), out=[];
  const add=x=>{if(!out.includes(x))out.push(x)};
  if(/壽險|保險/.test(s)) add('保險');
  if(/銀行|金控|信用卡|證券|金融/.test(s)) add('區域銀行');
  if(/晶圓|半導體|ic設計|asic|dram|flash|記憶體|封裝|探針|晶片|矽智財|矽晶圓|載板|砷化鎵/.test(s)) add('半導體');
  if(/ai伺服器|資料中心|雲端伺服器|白牌伺服器|伺服器管理/.test(s)){add('資料中心');add('人工智慧')}
  if(/工業自動化|氣動元件|自動化/.test(s)) add('工業自動化');
  if(/新藥|血癌|干擾素|生技/.test(s)) add('生技新藥');
  if(/醫療器材|精準醫療/.test(s)) add('醫療器材');
  if(/航空客運|航空貨運/.test(s)) add('航空');
  if(/遊戲|電競/.test(s)) add('遊戲電競');
  if(/零售|超商/.test(s)) add('零售');
  if(/太陽能/.test(s)) add('太陽能');
  if(/電動車/.test(s)) add('電動車');
  if(/資安/.test(s)) add('資安');
  if(/雲端/.test(s)) add('雲端運算');
  return out;
}
function validMetric(k,v){
  if(!Number.isFinite(v)||v<=0)return false;
  if(k==='pe')return v<=150;
  if(k==='ps')return v<=60;
  if(k==='pb')return v<=50;
  return false;
}
function metricWeights(cats){
  const financial=cats.length&&cats.every(c=>['區域銀行','保險','金融科技'].includes(c));
  return financial?{pb:.65,pe:.35}:{pe:.45,ps:.40,pb:.15};
}
function capRanks(rows){
  const x=rows.filter(r=>r.cap>0).sort((a,b)=>b.cap-a.cap), m=new Map(), d=Math.max(1,x.length-1);
  x.forEach((r,i)=>m.set(r.c,i/d)); return m;
}
function combineRatio(tw,bench,weights){
  let sw=0, sl=0, used=[];
  for(const [k,w] of Object.entries(weights)){
    const a=tw[k], b=bench[k];
    if(validMetric(k,a)&&validMetric(k,b)){sw+=w;sl+=w*Math.log(a/b);used.push(k.toUpperCase())}
  }
  return sw?{ratio:Math.exp(sl/sw),used}:null;
}

let computed=[];
async function main(){
  try{
    const [tw,us,twTags,usTags,twMeta,usMeta]=await Promise.all([
      getJSON('data/latest.json'),getJSON('data/us/latest.json'),getJSON('data/tags.json'),getJSON('data/us/tags.json'),
      getJSON('data/meta.json').catch(()=>({})),getJSON('data/us/meta.json').catch(()=>({}))
    ]);
    $('spreadAsOf').textContent=`台股 ${twMeta.asOf||'—'} ／ 美股 ${usMeta.asOf||'—'}`;
    const twRank=capRanks(tw), usRank=capRanks(us);
    const top=tw.filter(r=>r.cap>0).sort((a,b)=>b.cap-a.cap).slice(0,100);
    const usReady=us.filter(r=>r.cap>0&&!ADR_EXCLUDE.has(r.c));
    computed=top.map((r,idx)=>{
      const cats=classifyTw(r,twTags), weights=metricWeights(cats);
      let pool=usReady.filter(u=>{
        const ts=usTags[u.c]||[];
        return cats.some(c=>ts.includes(c)) && Object.keys(weights).some(k=>validMetric(k,u[k]));
      });
      if(!cats.length||pool.length<3)return {rank:idx+1,row:r,cats,matched:false,reason:!cats.length?'未建立可靠產業映射':'美股同業不足'};
      const rawBench={};
      for(const k of Object.keys(weights)){const vals=pool.map(x=>x[k]).filter(v=>validMetric(k,v));rawBench[k]=vals.length>=3?median(vals):null}
      const tg=twGrowth(r), tgpm=finVal(r,'gpm'), tnpm=finVal(r,'npm'), tsp=twRank.get(r.c)??0.5;
      const scored=pool.map(u=>{
        let d=0,den=0;
        const add=(a,b,scale,w)=>{if(Number.isFinite(a)&&Number.isFinite(b)){d+=w*clamp(Math.abs(a-b)/scale,0,2);den+=w}};
        add(tg,usGrowth(u),50,1.2); add(tgpm,finVal(u,'gpm'),40,1); add(tnpm,finVal(u,'npm'),30,1);
        add(tsp,usRank.get(u.c)??0.5,.20,1.1);
        d=den?d/den:9;
        return {u,d,w:Math.exp(-1.8*d)};
      }).sort((a,b)=>a.d-b.d).slice(0,12);
      const adjBench={};
      for(const k of Object.keys(weights)){
        const good=scored.filter(x=>validMetric(k,x.u[k]));
        adjBench[k]=good.length>=3?weightedMedian(good.map(x=>x.u[k]),good.map(x=>x.w)):null;
      }
      const raw=combineRatio(r,rawBench,weights), adj=combineRatio(r,adjBench,weights);
      if(!raw&&!adj)return {rank:idx+1,row:r,cats,matched:false,reason:'可比較估值指標不足'};
      const peers=scored.slice(0,5).map(x=>x.u);
      const metrics=(adj||raw).used;
      const conf=peers.length>=5&&metrics.length>=2?'高':peers.length>=3?'中':'低';
      return {rank:idx+1,row:r,cats,matched:true,peers,raw:raw?raw.ratio:null,adjusted:adj?adj.ratio:null,metrics,confidence:conf,poolCount:pool.length};
    });
    render();
  }catch(e){
    $('spreadBody').innerHTML=`<tr><td colspan="10">載入失敗：${esc(e.message)}</td></tr>`;
  }
}
function render(){
  const q=$('spreadQ').value.trim().toLowerCase(), st=$('spreadStatus').value, sort=$('spreadSort').value;
  let rows=computed.filter(x=>{
    if(st==='matched'&&!x.matched)return false;if(st==='unmatched'&&x.matched)return false;
    if(!q)return true; const hay=[x.row.c,x.row.n,x.row.i,...x.cats].join(' ').toLowerCase();return hay.includes(q);
  });
  rows.sort((a,b)=>{
    if(sort==='cap')return a.rank-b.rank;
    if(sort==='premium')return (b.adjusted??-999)-(a.adjusted??-999);
    if(sort==='raw')return (a.raw??999)-(b.raw??999);
    return (a.adjusted??999)-(b.adjusted??999);
  });
  const matched=computed.filter(x=>x.matched&&x.adjusted!=null), unmatched=100-matched.length;
  const med=median(matched.map(x=>(x.adjusted-1)*100));
  $('spreadKpis').innerHTML=`
    <div class="spread-kpi"><b>100</b><span>測試台股</span></div>
    <div class="spread-kpi"><b>${matched.length}</b><span>可計算價差</span></div>
    <div class="spread-kpi"><b>${unmatched}</b><span>暫無可靠對標</span></div>
    <div class="spread-kpi"><b class="${cls((med??0)/100)}">${fmtPct(med)}</b><span>可計算樣本中位價差</span></div>`;
  $('spreadBody').innerHTML=rows.map(x=>{
    const r=x.row;
    if(!x.matched)return `<tr class="spread-unmatched"><td>${x.rank}</td><td><strong>${esc(r.c)} ${esc(r.n)}</strong><br><small>${esc(r.i||'')}</small></td><td>${x.cats.length?x.cats.map(c=>`<span class="spread-pill">${esc(c)}</span>`).join(''):'—'}</td><td colspan="7">暫無可靠對標：${esc(x.reason)}</td></tr>`;
    const rawPct=x.raw==null?null:(x.raw-1)*100, adjPct=x.adjusted==null?null:(x.adjusted-1)*100;
    return `<tr><td>${x.rank}</td><td><strong>${esc(r.c)} ${esc(r.n)}</strong><br><small>${esc(r.i||'')}</small></td>
      <td>${x.cats.map(c=>`<span class="spread-pill">${esc(c)}</span>`).join('')}</td>
      <td class="peer-list">${x.peers.map(p=>`<strong>${esc(p.c)}</strong> ${esc(p.n)}`).join('<br>')}<br><small>候選 ${x.poolCount} 家</small></td>
      <td>${x.metrics.join(' / ')}</td><td><strong>1.00</strong></td>
      <td class="${cls((x.adjusted??1)-1)}"><strong>${fmtRel(x.adjusted)}</strong></td>
      <td class="${cls((x.raw??1)-1)}">${fmtPct(rawPct)}</td>
      <td class="${cls((x.adjusted??1)-1)}"><strong>${fmtPct(adjPct)}</strong></td><td>${x.confidence}</td></tr>`;
  }).join('');
}
['spreadQ','spreadStatus','spreadSort'].forEach(id=>$(id).addEventListener(id==='spreadQ'?'input':'change',render));
main();
})();