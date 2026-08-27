import unittest

from ai_video_pipeline.generation_harness import (
    HARNESS_SCHEMA,
    MAX_GENERATION_ATTEMPTS,
    VARIATION_STRATEGIES,
    harness_contract,
    retry_prompt,
    variation_strategy,
)


class GenerationHarnessTests(unittest.TestCase):
    def test_contract_uses_ten_sequential_varied_attempts(self):
        contract = harness_contract("image", "base-sha", ["identity matches"])

        self.assertEqual(contract["schema_version"], HARNESS_SCHEMA)
        self.assertEqual(contract["max_attempts"], 10)
        self.assertTrue(contract["stop_on_pass"])
        self.assertTrue(contract["vary_every_retry"])
        self.assertEqual(len(contract["variation_strategies"]), 10)
        self.assertEqual(len(set(contract["variation_strategies"])), 10)

    def test_every_retry_preserves_base_and_changes_strategy(self):
        base = "STRUCTURED BASE PROMPT"
        prompts = [retry_prompt(base, number, "repair identity")
                   for number in range(1, MAX_GENERATION_ATTEMPTS + 1)]

        self.assertEqual(prompts[0], base)
        self.assertEqual(len(set(prompts)), 10)
        for number, prompt in enumerate(prompts[1:], 2):
            self.assertTrue(prompt.startswith(base))
            self.assertIn(variation_strategy(number), prompt)
        self.assertEqual(tuple(VARIATION_STRATEGIES),
                         tuple(variation_strategy(i) for i in range(1, 11)))

    def test_fast_track_removes_only_internal_human_pause_from_terminal_failures(self):
        contract = harness_contract(
            "image", "base-sha", ["identity matches"], execution_mode="fast_track")
        self.assertEqual(contract["execution_mode"], "fast_track")
        self.assertNotIn("required_human_final_approval",
                         contract["terminal_failure_classes"])
        self.assertIn("permission_or_safety_boundary", contract["terminal_failure_classes"])


if __name__ == "__main__":
    unittest.main()
