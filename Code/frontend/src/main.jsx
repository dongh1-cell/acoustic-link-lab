import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {SignalChart,ComparisonChart} from './charts.jsx';
import {comparisonSeries} from './comparison.js';
import './style.css';

const labels={quiet:'安静',noise:'噪声',tone:'带内干扰'};
const fmt=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
const percent=v=>v==null?'—':`${(v*100).toFixed(1)}%`;
const fileUrl=(id,name,download=false)=>`/api/file?id=${encodeURIComponent(id)}&name=${name}${download?'&download=1':''}`;
const defaults={distance_m:'',system_volume:'',environment:'安静宿舍',playback_device:'魔霸新锐2023电脑扬声器',recording_device:'vivo X200s'};
function remembered(){try{return {...defaults,...JSON.parse(localStorage.getItem('acousticLab.conditions.v1')||'{}')}}catch{return defaults}}
async function api(path,body){
  const res=await fetch('/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Acoustic-Lab':'1'},body:JSON.stringify(body)}:{});
  const json=await res.json();if(!res.ok)throw new Error(json.error||'请求失败');return json;
}
function Status({row}){return <span className={row?.complete?'status good':'status'}>{row?.complete?'完整恢复':row?.decoded?'已解码':row?.recorded?'已录音':'待录音'}</span>}
function ExtraPoint({onAdded,notify,onBusyChange,operationBusy}){
  const [kind,setKind]=useState('noise'),[level,setLevel]=useState(.75),[ms,setMs]=useState(10),[text,setText]=useState(1),[busy,setBusy]=useState(false);
  async function add(e){e.preventDefault();setBusy(true);onBusyChange(true);try{const r=await api('add-point',{interference:kind,level:kind==='quiet'?0:Number(level),symbol_ms:Number(ms),text_index:Number(text)});await onAdded(r.ids[0]);notify('已加入两段补测音频。','success')}catch(e){notify(e.message)}finally{setBusy(false);onBusyChange(false)}}
  return <details className="extra"><summary>添加补测点</summary><p className="muted">在成功与失败之间补点，或用另一段文本复测。每次生成 BFSK、4FSK 各一段；强干扰时两方案采用相同幅度衰减。</p><form onSubmit={add}><fieldset disabled={busy||operationBusy}><div className="fields">
    <label>测试<select value={kind} onChange={e=>setKind(e.target.value)}>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
    <label>符号时长 / ms<input type="number" min="5" max="20" step=".5" required value={ms} onChange={e=>setMs(e.target.value)}/></label>
    {kind!=='quiet'&&<label>干扰 RMS 比例<input type="number" min=".01" max="20" step=".01" required value={level} onChange={e=>setLevel(e.target.value)}/></label>}
    <label>文本<select value={text} onChange={e=>setText(e.target.value)}>{[1,2,3].map(n=><option key={n} value={n}>{'ABC'[n-1]}</option>)}</select></label></div><button disabled={busy}>{busy?'生成中…':'加入录音清单'}</button></fieldset></form></details>;
}
function Analysis({notify,onAdded,onBusyChange,operationBusy}){
  const [data,setData]=useState(null),[kind,setKind]=useState('quiet'),[busy,setBusy]=useState(true);
  async function refresh(){setBusy(true);onBusyChange(true);try{setData(await api('summarize',{}))}catch(e){notify(e.message)}finally{setBusy(false);onBusyChange(false)}}
  useEffect(()=>{refresh()},[]);
  const rows=data?.groups||[],visible=comparisonSeries(rows,kind).flatMap(s=>s.rows);
  return <div className="analysis"><div className="section-title"><h2>结果汇总</h2><button onClick={refresh} disabled={busy||operationBusy}>{busy?'汇总中…':'更新结果'}</button></div>
    <p className="muted">已完成 {data?.completed_rounds??0} / {data?.planned_rounds??'—'} 段。每点显示实际样本量；10 ms 安静结果共用作两条干扰曲线的零点。</p>
    {!!data?.condition_mismatches?.length&&<p className="error">有 {data.condition_mismatches.length} 组采集条件不同，请核对距离、音量和设备记录。</p>}
    {!!data?.invalid_rounds?.length&&<p className="error">{data.invalid_rounds.map(r=>`${r.id}：${r.reason}`).join('；')}</p>}
    {!!data?.plan_issues?.length&&<p className="error">{data.plan_issues.join('；')}</p>}
    {!!data?.group_issues?.length&&<p className="error">{data.group_issues.join('；')}</p>}
    <div className="tabs small-tabs">{Object.entries(labels).map(([k,v])=><button key={k} aria-pressed={kind===k} className={kind===k?'active':''} onClick={()=>setKind(k)}>{k==='quiet'?'速率测试':v+'测试'}</button>)}</div>
    {!visible.length?<p className="empty">完成录音并导入后，这里显示对比曲线和统计表。</p>:<><div className="plots">{[['throughput_bps','有效吞吐','bit/s'],['text_recovery_rate','完整文本恢复率','%'],['loss_rate','丢包率','%'],['ber','误码率 BER','%']].map(([key,title,unit])=><ComparisonChart key={key} rows={rows} kind={kind} metric={key} title={title} unit={unit}/>)}</div>
      <p className="muted">首轮每点每方案采集1次，完整文本恢复率对应本轮成功或失败。录完后检查转折区域，必要时补点或复测。</p>
      <div className="table-scroll"><table><thead><tr><th>方案</th><th>时长 / ms</th><th>干扰</th><th>幅度</th><th>轮数</th><th>丢包 / 应发</th><th>错位 / 比较位</th><th>交付位 / 秒</th><th>全文恢复</th></tr></thead><tbody>{visible.map((r,i)=><tr key={i}><td>{r.scheme}</td><td>{r.symbol_ms}</td><td>{r.level}</td><td>{fmt(r.amplitude,4)}</td><td>{r.total_rounds}</td><td>{r.lost_packets}/{r.expected_packets}</td><td>{r.error_bits}/{r.compared_bits}</td><td>{r.delivered_bits}/{fmt(r.duration_s)}</td><td>{r.complete_rounds}/{r.total_rounds}</td></tr>)}</tbody></table></div></>}
    <ExtraPoint onAdded={onAdded} notify={notify} onBusyChange={onBusyChange} operationBusy={operationBusy}/>
  </div>;
}
function CustomExperiment({initial,onCreated,notify,onBusyChange}){
  const [text,setText]=useState(initial?.text||'DH 2023012159 Hello_IoT_2026! Round A: Sound carries data.'),[scheme,setScheme]=useState('BFSK'),[ms,setMs]=useState(10),[kind,setKind]=useState('quiet'),[level,setLevel]=useState(.5),[busy,setBusy]=useState(false);
  const valid=text.length>=40&&text.length<=80&&/^[\x20-\x7e]+$/.test(text);
  async function create(e){e.preventDefault();setBusy(true);onBusyChange(true);try{const r=await api('create',{text,scheme,symbol_ms:Number(ms),interference:kind,level:kind==='quiet'?0:Number(level)});await onCreated(r.id)}catch(e){notify(e.message)}finally{setBusy(false);onBusyChange(false)}}
  return <form className="custom-form" onSubmit={create}><fieldset disabled={busy}><h2>自定义发送</h2><label>发送文本<textarea value={text} onChange={e=>setText(e.target.value)} maxLength={80} rows="2" spellCheck="false"/></label><p className="caption">{text.length} 字符 · 请输入40～80个英文、数字、空格或英文标点。</p><div className="fields">
    <label>方案<select value={scheme} onChange={e=>setScheme(e.target.value)}><option>BFSK</option><option>4FSK</option></select></label><label>符号时长 / ms<input type="number" min="5" max="20" step=".5" required value={ms} onChange={e=>setMs(e.target.value)}/></label>
    <label>干扰<select value={kind} onChange={e=>setKind(e.target.value)}>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>{kind!=='quiet'&&<label>干扰 RMS 比例<input type="number" min=".01" max="20" step=".01" required value={level} onChange={e=>setLevel(e.target.value)}/></label>}</div><button className="primary" disabled={busy||!valid}>{busy?'生成中…':'生成发送音频'}</button><span className="caption"> 保存到自定义实验；正式补测可在“结果汇总”中添加。</span></fieldset></form>;
}
function App(){
  const [rows,setRows]=useState([]),[selected,setSelected]=useState(''),[run,setRun]=useState(null),[page,setPage]=useState('record'),[custom,setCustom]=useState(false);
  const [notice,setNotice]=useState(null),[runError,setRunError]=useState(''),[busy,setBusy]=useState(false),[signal,setSignal]=useState(null),[source,setSource]=useState('tx'),[mode,setMode]=useState('wave');
  const [file,setFile]=useState(null),[conditions,setConditions]=useState(remembered),audio=useRef();
  function notify(message,type='error'){setNotice({message,type})}
  async function reload(){const r=await api('experiments');setRows(r);return r}
  useEffect(()=>{reload().then(r=>{const first=r.find(x=>!x.error)||r[0];if(first)setSelected(first.id)}).catch(e=>notify(e.message))},[]);
  useEffect(()=>{if(!selected)return;let active=true;audio.current?.pause();setRun(null);setRunError('');setFile(null);setSignal(null);setSource('tx');const issue=rows.find(r=>r.id===selected)?.error;if(issue){setRunError(issue);return}api('experiment?id='+encodeURIComponent(selected)).then(r=>{if(active){setRun(r);setConditions(r.conditions||remembered())}}).catch(e=>{if(active){setRunError(e.message);notify(e.message)}});return()=>{active=false}},[selected]);
  useEffect(()=>{if(!run)return;let active=true;setSignal(null);api(`signal?id=${encodeURIComponent(run.id)}&kind=${source}`).then(s=>{if(active)setSignal(s)}).catch(e=>{if(active)notify(e.message)});return()=>{active=false}},[run,source]);
  function select(id){if(busy)return;audio.current?.pause();setSelected(id);setPage('record');setCustom(false);setNotice(null)}
  async function created(id){await reload();audio.current?.pause();setSelected(id);setPage('record');setCustom(false);setNotice(null)}
  function condition(key,value){setConditions(c=>({...c,[key]:value}))}
  async function importAudio(e){
    e.preventDefault();if(!file)return;if(file.size>60*1024*1024){notify('录音大小上限为60 MB。');return}
    setBusy(true);setNotice(null);audio.current?.pause();
    try{const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('录音文件读取失败'));reader.readAsDataURL(file)});
      const c={...conditions,distance_m:Number(conditions.distance_m),system_volume:Number(conditions.system_volume)};
      const r=await api('import',{id:selected,filename:file.name,audio:encoded,conditions:c});setRun(r);setSource('rx');await reload();try{localStorage.setItem('acousticLab.conditions.v1',JSON.stringify(c))}catch{}notify('录音已保存，解码完成。','success');
    }catch(e){notify(e.message)}finally{setBusy(false)}
  }
  async function decodeAgain(){setBusy(true);try{setRun(await api('decode',{id:selected}));await reload();notify('解码结果已更新。','success')}catch(e){notify(e.message)}finally{setBusy(false)}}
  const formal=rows.filter(r=>r.group==='formal'),others=rows.filter(r=>r.group!=='formal'),current=rows.find(r=>r.id===selected),m=run?.metrics,packets=run?.decoded?.packets||[];
  function list(items){return items.map(r=><button key={r.id} disabled={busy} className={`trial ${selected===r.id?'selected':''}`} aria-current={selected===r.id?'true':undefined} onClick={()=>select(r.id)}><span className="trial-number">{r.number?String(r.number).padStart(2,'0'):'·'}</span><span className="trial-label"><b>{r.scheme}</b><small className={r.error?'error':''}>{r.error?'文件待修复':`${labels[r.interference]}${r.level?` ${r.level}`:''} · ${r.symbol_ms} ms`}</small></span><span className={r.error?'error':r.recorded?'recorded':'pending'} aria-label={r.error?'文件待修复':r.recorded?'已录音':'待录音'}>{r.error?'!':r.recorded?'✓':'○'}</span></button>)}
  return <div className="app"><header className="header"><h1>声波通信实验</h1><nav className="tabs" aria-label="页面"><button disabled={busy} className={page==='record'?'active':''} onClick={()=>setPage('record')}>录音实验</button><button disabled={busy} className={page==='results'?'active':''} onClick={()=>{audio.current?.pause();setPage('results')}}>结果汇总</button></nav></header>
    {notice&&<div className={`notice ${notice.type}`} role="alert"><span>{notice.message}</span><button aria-label="关闭提示" onClick={()=>setNotice(null)}>×</button></div>}
    <div className="layout"><aside className="sidebar"><div className="list-heading"><h2>录音清单</h2><span>{formal.filter(r=>r.recorded).length}/{formal.length}</span></div><p className="caption">按编号录制，相邻两段为一组。</p><div className="trial-list">{list(formal)}</div>{!!others.length&&<details><summary>其他实验（{others.length}）</summary>{list(others)}</details>}<button className="custom-button" disabled={busy} onClick={()=>{audio.current?.pause();setPage('record');setCustom(v=>!v)}}>{custom?'收起自定义':'自定义发送'}</button></aside>
    <main>{page==='results'?<Analysis notify={notify} onAdded={created} onBusyChange={setBusy} operationBusy={busy}/>:<>
      {custom&&<CustomExperiment key={selected} initial={run} onCreated={created} notify={notify} onBusyChange={setBusy}/>}
      {!run?<p className={runError?'empty error':'empty'} role={runError?'alert':undefined}>{runError|| (selected?'正在读取实验…':'等待实验清单。请运行 Code/initialize.py。')}</p>:<>
        <div className="section-title run-heading"><div><h2>{current?.number?`${String(current.number).padStart(2,'0')} · `:''}{run.config.scheme}<span className="run-condition">{labels[run.transmission.interference]}{run.transmission.interference_rms_ratio?` ${run.transmission.interference_rms_ratio}`:''} · {run.config.symbol_ms} ms</span></h2><p className="caption">{current?.number?`录音命名：${String(current.number).padStart(2,'0')}_${run.config.scheme}`:current?.name} · 播放 {fmt(run.transmission.duration_s)} 秒</p></div><Status row={current}/></div>
        <section className="section"><h3>1. 播放并录音</h3><p className="instructions">手机开始录音，等2秒再播放；播放结束后再录2秒。保持设备位置和电脑音量相同。</p><p className="send-text">{run.text}</p>
          <div className="player"><audio key={selected} ref={audio} controls preload="metadata" src={fileUrl(selected,'tx.wav')} aria-label="播放发送音频"/><a href={fileUrl(selected,'tx.wav',true)}>下载 tx.wav</a></div>
          <details className="config"><summary>协议参数与文件位置</summary><dl><dt>采样率 / 包间隔</dt><dd>{run.config.sample_rate} Hz / {run.config.gap_s} s</dd><dt>信号幅度</dt><dd>{fmt(run.config.amplitude,4)}</dd><dt>载波</dt><dd>{run.config.scheme==='BFSK'?'2 / 3':'1.5 / 2 / 2.5 / 3'} kHz</dd><dt>校验 / 纠错</dt><dd>{run.config.scheme==='BFSK'?'异或校验':`CRC-16 / ${run.config.coding==='hamming15_11'?'Hamming(15,11)＋交织':'无'}`}</dd><dt>分包</dt><dd>{run.text.length} 字符 / {Math.ceil(run.text.length/10)} 包，每包最多10字符</dd><dt>保存位置</dt><dd className="mono">Data/{run.id}/</dd></dl></details>
          <div className="signal-tools"><label>信号<select value={source} onChange={e=>setSource(e.target.value)}><option value="tx">发送 TX</option><option value="rx" disabled={!run.recorded}>接收 RX</option></select></label><div className="tabs small-tabs"><button className={mode==='wave'?'active':''} onClick={()=>setMode('wave')}>波形</button><button className={mode==='spectrum'?'active':''} onClick={()=>setMode('spectrum')}>频谱</button></div><span className="caption">{signal?fmt(signal.duration_s)+' s':''} · {mode==='wave'?'时间 / s，振幅':'频率 / Hz，功率谱 / dB'}</span></div><SignalChart data={signal} mode={mode} scheme={run.config.scheme}/>
        </section>
        <section className="section"><h3>2. 导入手机录音</h3>{run.recorded?<div className="imported"><p>已保存本轮录音。距离 {run.conditions?.distance_m} m，音量 {run.conditions?.system_volume}%，{run.conditions?.environment}。</p><div className="actions"><a href={fileUrl(selected,'rx.wav',true)}>下载 rx.wav</a><button disabled={busy} onClick={decodeAgain}>{busy?'解码中…':'重新解码'}</button></div></div>:<form onSubmit={importAudio}><fieldset disabled={busy}><label className="file-field">选择本轮完整录音<input key={selected} type="file" required accept=".wav,.m4a,.mp4a,.mp3,.aac,.mp4" onChange={e=>setFile(e.target.files[0]||null)}/></label><div className="fields recording-fields"><label>实际距离 / m<input required type="number" min=".01" step=".01" value={conditions.distance_m} onChange={e=>condition('distance_m',e.target.value)} placeholder="如 0.70"/></label><label>电脑音量 / %<input required type="number" min="1" max="100" step="1" value={conditions.system_volume} onChange={e=>condition('system_volume',e.target.value)} placeholder="如 50"/></label><label>环境<input required value={conditions.environment} onChange={e=>condition('environment',e.target.value)}/></label></div>
          <details className="devices"><summary>{conditions.playback_device} → {conditions.recording_device}</summary><div className="fields"><label>播放设备<input required value={conditions.playback_device} onChange={e=>condition('playback_device',e.target.value)}/></label><label>录音设备<input required value={conditions.recording_device} onChange={e=>condition('recording_device',e.target.value)}/></label></div></details><button className="primary" disabled={!file||busy}>{busy?'正在解码…':'导入并解码'}</button></fieldset></form>}</section>
        <section className="section results"><div className="section-title"><h3>3. 解码结果</h3>{run.decoded&&<a href={fileUrl(selected,'rec.txt',true)}>下载 rec.txt</a>}</div>{!run.decoded?<p className="muted">导入后显示恢复文本、逐包结果和性能指标。</p>:<>
          <div className="text-pair"><div><span>发送原文</span><p>{run.text}</p></div><div><span>恢复文本</span><p>{run.decoded.display_text||'本轮未恢复出文本。'}</p></div></div>
          <div className="metrics">{[['丢包率',percent(m?.loss_rate),`${m?.lost_packets}/${m?.expected_packets} 包`],['BER',percent(m?.ber),`${m?.error_bits}/${m?.compared_bits} 位`],['有效吞吐',`${fmt(m?.throughput_bps)} bit/s`,`${m?.delivered_bits} 位 / ${fmt(m?.duration_s)} s`],['完整文本恢复率',percent(m?.text_recovery_rate),`${m?.complete_rounds}/${m?.total_rounds} 轮`]].map(([label,value,note])=><div key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>)}</div>
          <div className="table-scroll"><table><thead><tr><th>包序号</th><th>长度</th><th>同步</th><th>校验</th><th>解码文本</th></tr></thead><tbody>{packets.map((p,i)=><tr key={i}><td>{p.seq}/{p.total}</td><td>{p.length} B</td><td>已同步 · {fmt(p.start_s,3)} s</td><td className={p.checksum_ok?'good':'error'}>{p.checksum_ok?'通过':'失败'}</td><td className="mono">{p.text}</td></tr>)}</tbody></table></div>{!packets.length&&<p className="muted">未检测到有效数据包，请核对录音与所选实验。</p>}
          {run.decoded.coding==='hamming15_11'&&<details className="config"><summary>纠错统计</summary><p>纠错前 Payload：{m?.pre_fec_error_bits}/{m?.pre_fec_compared_bits} 错误位；共 {m?.fec_correction_attempts} 次码字修正尝试。</p><p className="caption">{packets.map(p=>`包${p.seq}：${p.fec_correction_attempts}/${p.fec_codewords} 码字`).join('；')}</p></details>}
        </>}</section>
      </>}
    </>}</main></div>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
