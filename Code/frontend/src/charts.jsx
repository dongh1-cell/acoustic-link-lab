import React, {useState,useEffect,useRef} from 'react';
import {comparisonSeries} from './comparison.js';
const fmt=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
const percent=v=>v==null?'—':`${(v*100).toFixed(1)}%`;
function Empty({title,children}){return <div className="empty"><p>{title}</p><p>{children}</p></div>}
export function SignalChart({data,mode,scheme}){
  const chartRef=useRef(null),[chartWidth,setChartWidth]=useState(800);
  useEffect(()=>{if(!chartRef.current)return;const observer=new ResizeObserver(entries=>setChartWidth(entries[0].contentRect.width));observer.observe(chartRef.current);return()=>observer.disconnect()},[data]);
  if(!data)return <div className="chart-loading"> 正在读取信号</div>;
  const labelSize=Math.min(32,Math.max(10,10000/chartWidth)),viewHeight=Math.max(212,Math.min(440,212*650/chartWidth));
  const left=18+labelSize*3,right=1000-labelSize*1.7,top=18,bottom=viewHeight-34;
  const spectrum=mode==='spectrum';const duration=data.duration_s;
  const scale=Math.max(.05,data.peak)*1.1;
  const x=t=>left+t/(spectrum?5000:duration)*(right-left);
  const y=v=>spectrum?bottom-(Math.max(-130,Math.min(-15,v))+130)/115*(bottom-top):(top+bottom)/2-v/scale*(bottom-top)/2;
  const ticks=spectrum?[0,1000,2000,3000,4000,5000]:Array.from({length:6},(_,i)=>duration*i/5);
  const points=spectrum?data.spectrum.map(([t,v])=>`${x(t)},${y(v)}`):null;
  const high=!spectrum?data.wave.map(([t,lo,hi])=>`${x(t)},${y(hi)}`):[];
  const low=!spectrum?[...data.wave].reverse().map(([t,lo])=>`${x(t)},${y(lo)}`):[];
  const color=scheme==='4FSK'?'#327b61':'#3f6daa';
  return <svg ref={chartRef} className="signal-chart" style={{'--chart-label-size':`${labelSize}px`}} viewBox={`0 0 1000 ${viewHeight}`} role="img" aria-label={spectrum?'当前音频的功率谱':'当前音频的完整时域波形'}>
    <defs><linearGradient id="signalFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".18"/><stop offset="100%" stopColor={color} stopOpacity=".02"/></linearGradient></defs>
    {[top,(top+bottom)/2,bottom].map((v,i)=><g key={v}><line x1={left} y1={v} x2={right} y2={v} stroke="#e8e9e4" strokeDasharray={i===1?'0':'3 4'}/><text x={left-12} y={v+4} textAnchor="end">{spectrum?['−15','−73','−130'][i]:[fmt(scale,2),'0',fmt(-scale,2)][i]}</text></g>)}
    {ticks.map((t,i)=><g key={i}><line x1={x(t)} y1={top} x2={x(t)} y2={bottom} stroke="#eeeee9"/><text x={x(t)} y={viewHeight-10} textAnchor="middle">{spectrum?`${t/1000}k`:fmt(t,1)}</text></g>)}
    {spectrum?<><polygon points={`${left},${bottom} ${points.join(' ')} ${right},${bottom}`} fill="url(#signalFill)"/><polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="1.8"/></>:<polygon points={[...high,...low].join(' ')} fill={color} fillOpacity=".72" stroke={color} strokeWidth=".4"/>}
  </svg>;
}

export function ComparisonChart({rows,kind,metric,title,unit}){
  const sets=comparisonSeries(rows,kind);
  const all=sets.flatMap(s=>s.rows),xx=r=>kind==='quiet'?1000/r.symbol_ms:r.level,values=all.filter(r=>r[metric]!=null);
  const maxX=Math.max(1,...all.map(xx)),minX=Math.min(0,...all.map(xx)),maxY=unit==='%'?1:Math.max(1,...values.map(r=>r[metric]))*1.15;
  const x=r=>40+(xx(r)-minX)/(maxX-minX)*390,y=r=>170-r[metric]/maxY*140;
  return <section className="panel comparison-chart"><div className="section-heading"><h2>{title}</h2><span className="mono muted">{unit}</span></div>{!all.length?<Empty title="等待本项测试结果">采集这一条件的录音后生成曲线。</Empty>:<><svg viewBox="0 0 460 205" role="img" aria-label={title+'对比曲线'}>{[0,.5,1].map(v=><g key={v}><line x1="40" y1={170-v*140} x2="435" y2={170-v*140} stroke="#e5e7e0"/><text x="30" y={174-v*140} textAnchor="end">{unit==='%'?Math.round(v*100):fmt(v*maxY,0)}</text></g>)}{sets.map(set=><g key={set.label} fill={set.color} stroke={set.color}><polyline points={set.rows.filter(r=>r[metric]!=null).map(r=>`${x(r)},${y(r)}`).join(' ')} fill="none" strokeWidth="2" strokeDasharray={set.dash}/>{set.rows.filter(r=>r[metric]!=null).map((r,j)=><circle key={j} cx={x(r)} cy={y(r)} r="3"><title>{set.label}: {unit==='%'?percent(r[metric]):fmt(r[metric])}，{r.total_rounds}轮</title></circle>)}</g>)}{[...new Set(all.map(xx))].map(v=><text key={v} x={40+(v-minX)/(maxX-minX)*390} y="193" textAnchor="middle">{fmt(v,1)}</text>)}</svg><div className="chart-legend" style={{flexWrap:'wrap'}}>{sets.map(set=><span key={set.label} style={{color:set.color}}>{set.label}</span>)}<small>{kind==='quiet'?'符号速率 / symbols·s⁻¹':'播放端干扰 RMS 比例'}</small></div></>}</section>
}
