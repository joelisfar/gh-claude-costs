"""Standalone tests for extract.py — uses unittest from stdlib only.

Run with: python3 test_extract.py
"""
import json
import unittest
from io import BytesIO
from unittest.mock import patch

import extract


class TestNormalizeModel(unittest.TestCase):
    def test_strips_date_suffix(self):
        self.assertEqual(extract.normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5")

    def test_no_suffix_unchanged(self):
        self.assertEqual(extract.normalize_model("claude-opus-4-7"), "claude-opus-4-7")

    def test_synthetic_returns_none(self):
        self.assertIsNone(extract.normalize_model("<synthetic>"))


class TestFetchLitellmPricing(unittest.TestCase):
    def test_returns_empty_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(extract.fetch_litellm_pricing(), {})

    def test_returns_empty_on_malformed_json(self):
        bad = BytesIO(b"not json")
        with patch("urllib.request.urlopen", return_value=bad):
            self.assertEqual(extract.fetch_litellm_pricing(), {})

    def test_parses_anthropic_entries_and_skips_others(self):
        sample = {
            "claude-opus-4-7": {
                "litellm_provider": "anthropic",
                "input_cost_per_token": 5e-6,
                "output_cost_per_token": 25e-6,
                "cache_read_input_token_cost": 5e-7,
                "cache_creation_input_token_cost": 6.25e-6,
            },
            "anthropic.claude-opus-4-7": {  # bedrock variant — skip
                "litellm_provider": "bedrock_converse",
                "input_cost_per_token": 5e-6,
                "output_cost_per_token": 25e-6,
                "cache_read_input_token_cost": 5e-7,
                "cache_creation_input_token_cost": 6.25e-6,
            },
            "gpt-5": {
                "litellm_provider": "openai",
                "input_cost_per_token": 1e-6,
            },
        }
        body = BytesIO(json.dumps(sample).encode("utf-8"))
        with patch("urllib.request.urlopen", return_value=body):
            result = extract.fetch_litellm_pricing()
        self.assertIn("claude-opus-4-7", result)
        self.assertNotIn("anthropic.claude-opus-4-7", result)
        self.assertNotIn("gpt-5", result)
        rates = result["claude-opus-4-7"]
        self.assertEqual(rates["base"], 5.0)
        self.assertEqual(rates["output"], 25.0)
        self.assertEqual(rates["cache_read"], 0.5)
        self.assertEqual(rates["cache_write_5m"], 6.25)
        self.assertEqual(rates["cache_write_1h"], 10.0)  # derived = base*2

    def test_skips_entry_missing_required_field(self):
        sample = {
            "claude-opus-4-7": {
                "litellm_provider": "anthropic",
                "input_cost_per_token": 5e-6,
                # missing output_cost_per_token, cache_*
            },
        }
        body = BytesIO(json.dumps(sample).encode("utf-8"))
        with patch("urllib.request.urlopen", return_value=body):
            result = extract.fetch_litellm_pricing()
        self.assertEqual(result, {})

    def test_normalizes_date_suffixed_keys(self):
        sample = {
            "claude-haiku-4-5-20251001": {
                "litellm_provider": "anthropic",
                "input_cost_per_token": 1e-6,
                "output_cost_per_token": 5e-6,
                "cache_read_input_token_cost": 1e-7,
                "cache_creation_input_token_cost": 1.25e-6,
            },
        }
        body = BytesIO(json.dumps(sample).encode("utf-8"))
        with patch("urllib.request.urlopen", return_value=body):
            result = extract.fetch_litellm_pricing()
        self.assertIn("claude-haiku-4-5", result)
        self.assertNotIn("claude-haiku-4-5-20251001", result)


class TestFallbackPricing(unittest.TestCase):
    def test_includes_opus_4_7(self):
        self.assertIn("claude-opus-4-7", extract.FALLBACK_PRICING)

    def test_haiku_4_5_uses_correct_anthropic_rates(self):
        # Was incorrectly priced at Haiku 3.5 rates ($0.80/$4); fixed to $1/$5.
        rates = extract.FALLBACK_PRICING["claude-haiku-4-5"]
        self.assertEqual(rates["base"], 1.00)
        self.assertEqual(rates["output"], 5.00)

    def test_1h_cache_rate_is_2x_base(self):
        for model, rates in extract.FALLBACK_PRICING.items():
            self.assertAlmostEqual(rates["cache_write_1h"], rates["base"] * 2.0, places=4,
                                   msg=f"{model}: 1h cache rate must be 2x base")

    def test_5m_cache_rate_is_1_25x_base_except_haiku_3_5(self):
        # Haiku 3.5 has historical pricing where 5m write = $1.00 vs $0.80 base
        # (1.25x exactly = 1.00, so this works), but verify all entries.
        for model, rates in extract.FALLBACK_PRICING.items():
            self.assertAlmostEqual(rates["cache_write_5m"], rates["base"] * 1.25, places=4,
                                   msg=f"{model}: 5m cache rate must be 1.25x base")


if __name__ == "__main__":
    unittest.main()
