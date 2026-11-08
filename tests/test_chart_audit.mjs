import assert from 'node:assert/strict';
import {metricSegments} from '../Code/frontend/src/comparison.js';
const points=[0,0.1,null,0.2,undefined,0.3,0.4].map((ber,index)=>({ber,index}));
assert.deepEqual(metricSegments(points,'ber').map(segment=>segment.map(row=>row.index)),[[0,1],[3],[5,6]]);
assert.deepEqual(metricSegments([{ber:null},{ber:NaN}],'ber'),[]);
assert.equal(metricSegments([{ber:0}],'ber')[0][0].ber,0);
console.log('PASS: BER curves preserve gaps at points without comparable bits');
