"""Post-decode assessment; reference text never enters the receiver."""
import numpy as np
from protocol import split_text


def assess(text, reception, duration_s):
    expected = split_text(text)
    successes, delivered, errors, compared = 0, 0, 0, 0
    raw_errors=0;correction_attempts=0
    details = []
    for seq, payload in enumerate(expected, 1):
        candidates = [p for p in reception['packets'] if p['seq']==seq and
                      p['total']==len(expected) and p['length']==len(payload)]
        # One representative per logical packet, chosen using received evidence.
        p = max(candidates, key=lambda p:(p['checksum_ok'],p['sync_score'])) if candidates else None
        ok = bool(p and p['checksum_ok'] and bytes.fromhex(p['payload_hex'])==payload
                  and seq not in reception['conflicting_sequences'])
        successes += int(ok)
        delivered += len(payload)*8 if ok else 0
        if p:
            received = bytes.fromhex(p['payload_hex'])
            wrong = sum((a^b).bit_count() for a,b in zip(payload, received))
            bits = len(payload)*8
            errors += wrong
            raw_payload=bytes.fromhex(p.get('raw_payload_hex',p['payload_hex']))
            raw_errors+=sum((a^b).bit_count() for a,b in zip(payload,raw_payload))
            correction_attempts+=p.get('fec_correction_attempts',0)
            compared += bits
        else:
            wrong, bits = None, 0
        details.append(dict(seq=seq, successful=ok, aligned=bool(p),
                            error_bits=wrong, compared_bits=bits))
    full = reception['recovered_text']==text
    return dict(expected_packets=len(expected), successful_packets=successes,
                lost_packets=len(expected)-successes, loss_rate=(len(expected)-successes)/len(expected),
                error_bits=errors, compared_bits=compared, ber=errors/compared if compared else None,
                ber_scope='最终Payload位；总包数、序号和长度对齐，含校验失败包，每个逻辑包比较一次',
                pre_fec_error_bits=raw_errors,pre_fec_compared_bits=compared,
                pre_fec_ber=raw_errors/compared if compared else None,
                fec_correction_attempts=correction_attempts,
                delivered_bits=delivered, duration_s=duration_s, throughput_bps=delivered/duration_s,
                complete_rounds=int(full), total_rounds=1, text_recovery_rate=float(full), packets=details)


def aggregate(rows):
    keys = ['expected_packets','successful_packets','lost_packets','error_bits','compared_bits',
            'delivered_bits','duration_s','complete_rounds','total_rounds',
            'pre_fec_error_bits','pre_fec_compared_bits','fec_correction_attempts']
    out = {key:sum(row.get(key,0) for row in rows) for key in keys}
    out.update(loss_rate=out['lost_packets']/out['expected_packets'] if out['expected_packets'] else None,
               ber=out['error_bits']/out['compared_bits'] if out['compared_bits'] else None,
               pre_fec_ber=out['pre_fec_error_bits']/out['pre_fec_compared_bits'] if out['pre_fec_compared_bits'] else None,
               throughput_bps=out['delivered_bits']/out['duration_s'] if out['duration_s'] else None,
               text_recovery_rate=out['complete_rounds']/out['total_rounds'] if rows else None)
    return out
