export function comparisonSeries(rows,kind){
  const rates=kind==='quiet'?[null]:[...new Set(rows.filter(r=>r.interference===kind).map(r=>r.symbol_ms))].sort((a,b)=>a-b);
  return ['BFSK','4FSK'].flatMap(scheme=>rates.map((rate,index)=>({
    label:rate===null?scheme:`${scheme} · ${rate} ms`,
    color:scheme==='BFSK'?'#3f6daa':'#327b61',
    dash:['','6 3','2 3','8 3 2 3'][index%4],
    rows:rows.filter(r=>r.scheme===scheme&&(kind==='quiet'?r.interference==='quiet':
      r.symbol_ms===rate&&(r.interference===kind||r.interference==='quiet')))
      .sort((a,b)=>kind==='quiet'?b.symbol_ms-a.symbol_ms:a.level-b.level)
  }))).filter(series=>series.rows.length);
}

// An unavailable BER has zero comparable payload bits. Preserve a visible gap
// instead of connecting the measurements on either side of that point.
export function metricSegments(rows,metric){
  const segments=[];let current=[];
  for(const row of rows){
    if(row[metric]==null||!Number.isFinite(row[metric])){
      if(current.length)segments.push(current);
      current=[];
    }else current.push(row);
  }
  if(current.length)segments.push(current);
  return segments;
}
