import assert from 'node:assert/strict';
import {comparisonSeries} from '../Code/frontend/src/comparison.js';
const rows=['BFSK','4FSK'].flatMap(scheme=>[5,10].flatMap(symbol_ms=>[
  {scheme,symbol_ms,interference:'quiet',level:0},
  {scheme,symbol_ms,interference:'noise',level:0.5},
  {scheme,symbol_ms,interference:'noise',level:1}
]));
const noise=comparisonSeries(rows,'noise');
assert.equal(noise.length,4);
for(const series of noise){
  assert.equal(new Set(series.rows.map(r=>r.symbol_ms)).size,1);
  assert.equal(new Set(series.rows.map(r=>r.scheme)).size,1);
  assert.deepEqual(series.rows.map(r=>r.level),[0,0.5,1]);
}
assert.equal(comparisonSeries(rows,'quiet').length,2);
assert.deepEqual(comparisonSeries(rows,'tone'),[]);
console.log('PASS: interference curves separate symbol durations and match their own quiet baseline');
