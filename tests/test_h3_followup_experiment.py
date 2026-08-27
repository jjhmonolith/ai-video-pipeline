import unittest
from pathlib import Path

from ai_video_pipeline.h3_followup_experiment import _l1_manifest, _m1_manifest


ROOT = Path(__file__).resolve().parents[1]


class H3FollowupExperimentTests(unittest.TestCase):
    def test_factorial_counts_and_canary_split_match_the_design(self):
        manifests = [_l1_manifest(ROOT), _m1_manifest(ROOT)]
        self.assertEqual([len(item["records"]) for item in manifests], [18, 24])
        records = [record for manifest in manifests for record in manifest["records"]]
        self.assertEqual(sum(record["phase"] == "pilot" for record in records), 14)
        self.assertEqual(sum(record["phase"] == "main" for record in records), 28)
        self.assertTrue(all(record["h3_native_audio"] == "discard" for record in records))

    def test_l1_anchor_pairs_change_only_the_last_frame(self):
        records = _l1_manifest(ROOT)["records"]
        for camera in {item["factors"]["camera_policy"] for item in records}:
            for seed_index in (1, 2, 3):
                pair = [item for item in records
                        if item["factors"]["camera_policy"] == camera
                        and item["factors"]["seed_index"] == seed_index]
                self.assertEqual(len(pair), 2)
                self.assertEqual(len({item["seed"] for item in pair}), 1)
                self.assertEqual(len({item["prompt_sha256"] for item in pair}), 1)
                self.assertEqual(len({item["first_frame"]["sha256"] for item in pair}), 1)
                self.assertEqual(len({tuple(ref["sha256"] for ref in item["references"])
                                      for item in pair}), 1)
                self.assertEqual(sum(item["last_frame"] is not None for item in pair), 1)

    def test_m1_reference_and_anchor_axes_are_isolated(self):
        records = _m1_manifest(ROOT)["records"]
        identity = [item for item in records
                    if item["factors"]["reference_pack"] == "identity_only"]
        affordance = [item for item in records
                      if item["factors"]["reference_pack"] == "identity_plus_affordance"]
        self.assertTrue(all(len(item["references"]) == 1 for item in identity))
        self.assertTrue(all(len(item["references"]) == 2 for item in affordance))
        for task in {item["factors"]["task"] for item in records}:
            for pack in {item["factors"]["reference_pack"] for item in records}:
                for seed_index in (1, 2, 3):
                    pair = [item for item in records
                            if item["factors"]["task"] == task
                            and item["factors"]["reference_pack"] == pack
                            and item["factors"]["seed_index"] == seed_index]
                    self.assertEqual(len(pair), 2)
                    self.assertEqual(len({item["prompt_sha256"] for item in pair}), 1)
                    self.assertEqual(sum(item["last_frame"] is not None for item in pair), 1)


if __name__ == "__main__":
    unittest.main()
