"""Receiver checks for unequal carrier response and carrier-local background."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Code'))
import protocol
from protocol import Config, transmit
from receiver import decode


class ReceiverEqualizationTests(unittest.TestCase):
    def frequency_selective_recording(self, text, symbol_ms):
        cfg = Config(scheme='4FSK', coding='hamming15_11', symbol_ms=symbol_ms)
        original_modulator = protocol.modulate_symbols

        def channel_modulator(values, config):
            # Idealized per-band attenuation: the 1500-Hz path has 0.49%
            # of the 3000-Hz power. Apply it to the whole packet, including
            # its preamble, so the receiver must estimate it from the signal.
            count = round(config.sample_rate * config.symbol_ms / 1000)
            response = np.array([.07, .16, .25, 1.0])[values]
            return original_modulator(values, config) * np.repeat(response, count)

        with patch.object(protocol, 'modulate_symbols', channel_modulator):
            signal, _ = transmit(text, cfg)
        # A persistent in-band source remains present between the packets.
        time = np.arange(len(signal)) / cfg.sample_rate
        signal = signal + .02 * np.sin(2 * np.pi * 2000 * time)
        return np.r_[np.zeros(12345), signal, np.zeros(7211)], cfg

    def test_unequal_carriers_with_inband_background(self):
        text = 'Public channel test: 4826 values through four tones.'
        signal, cfg = self.frequency_selective_recording(text, 10)
        result = decode(signal, cfg.sample_rate, cfg)
        self.assertEqual(result['recovered_text'], text)
        self.assertTrue(all(packet['checksum_ok'] for packet in result['packets']))

    def test_short_symbols_with_unequal_carriers(self):
        rng = np.random.default_rng(73621)
        text = ''.join(chr(int(value)) for value in rng.integers(32, 127, 57))
        signal, cfg = self.frequency_selective_recording(text, 5)
        result = decode(signal, cfg.sample_rate, cfg)
        self.assertEqual(result['recovered_text'], text)
        self.assertEqual(len(result['packets']), 6)

    def test_background_only_produces_no_valid_packets(self):
        rate = 48000
        time = np.arange(3 * rate) / rate
        samples = {
            'silence': np.zeros(3 * rate),
            'tone': .2 * np.sin(2 * np.pi * 2000 * time),
            'noise': np.random.default_rng(6627).normal(0, .1, 3 * rate),
        }
        for scheme in ('BFSK', '4FSK'):
            cfg = Config(scheme=scheme,
                         coding='hamming15_11' if scheme == '4FSK' else 'none')
            for name, signal in samples.items():
                with self.subTest(scheme=scheme, background=name):
                    result = decode(signal, rate, cfg)
                    self.assertFalse(result['complete'])
                    self.assertIsNone(result['recovered_text'])
                    self.assertFalse(any(p['checksum_ok'] for p in result['packets']))


if __name__ == '__main__':
    unittest.main()
