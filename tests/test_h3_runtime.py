import unittest

from ai_video_pipeline.h3_runtime import (
    H3Request,
    H3RuntimeError,
    H3Settings,
    _iter_output_files,
    build_workflow,
    snap_length,
)


class FrameGridTests(unittest.TestCase):
    def test_durations_snap_up_to_the_17k_plus_5_grid(self):
        self.assertEqual(snap_length(0.0), 5)
        self.assertEqual(snap_length(1.0), 39)  # 24 -> next valid is 39
        self.assertEqual(snap_length(2.0), 56)  # 48 -> 56
        self.assertEqual(snap_length(5.0), 124)  # exactly on grid
        for seconds in (0.5, 1.3, 3.7, 8.0, 15.0):
            self.assertEqual((snap_length(seconds) - 5) % 17, 0)

    def test_snapping_never_shortens_the_request(self):
        for seconds in (1.0, 2.5, 6.0, 9.9):
            self.assertGreaterEqual(snap_length(seconds), round(seconds * 24))


class WorkflowGraphTests(unittest.TestCase):
    def test_text_to_video_graph_wires_dual_vae_decode_into_one_muxed_video(self):
        graph = build_workflow(H3Request(prompt="a lantern drifting over still water", seconds=2.0))

        self.assertEqual(graph["conditioning"]["class_type"], "MiniMaxH3ImageToVideo")
        self.assertEqual(graph["conditioning"]["inputs"]["length"], 56)
        self.assertNotIn("first_frame", graph["conditioning"]["inputs"])
        # Both decoders read the same AV latent, split by their respective VAEs.
        self.assertEqual(graph["decode_video"]["inputs"]["samples"], ["sample", 0])
        self.assertEqual(graph["decode_audio"]["inputs"]["samples"], ["sample", 0])
        self.assertEqual(graph["decode_video"]["inputs"]["vae"], ["video_vae", 0])
        self.assertEqual(graph["decode_audio"]["inputs"]["vae"], ["audio_vae", 0])
        self.assertEqual(graph["mux"]["inputs"]["images"], ["decode_video", 0])
        self.assertEqual(graph["mux"]["inputs"]["audio"], ["decode_audio", 0])
        self.assertEqual(graph["save"]["inputs"]["video"], ["mux", 0])

    def test_sampling_is_cfg_free_and_reads_the_conditioning_latent(self):
        graph = build_workflow(H3Request(prompt="x"))
        self.assertEqual(graph["guider"]["class_type"], "BasicGuider")
        self.assertEqual(graph["sample"]["inputs"]["latent_image"], ["conditioning", 1])
        self.assertEqual(graph["sigmas"]["inputs"]["denoise"], 1.0)
        self.assertEqual(graph["clip"]["inputs"]["type"], "minimax")

    def test_turbo_lora_sits_between_the_unet_and_every_model_consumer(self):
        graph = build_workflow(H3Request(prompt="x"))
        self.assertEqual(graph["turbo_lora"]["inputs"]["model"], ["unet", 0])
        self.assertEqual(graph["sigmas"]["inputs"]["model"], ["turbo_lora", 0])
        self.assertEqual(graph["guider"]["inputs"]["model"], ["turbo_lora", 0])

    def test_disabling_turbo_removes_the_lora_and_raises_the_step_count(self):
        settings = H3Settings().without_turbo()
        graph = build_workflow(H3Request(prompt="x"), settings)
        self.assertNotIn("turbo_lora", graph)
        self.assertEqual(graph["sigmas"]["inputs"]["model"], ["unet", 0])
        self.assertEqual(graph["guider"]["inputs"]["model"], ["unet", 0])
        self.assertEqual(graph["sigmas"]["inputs"]["steps"], 20)

    def test_anchor_frames_add_loaders_wired_into_the_conditioning_node(self):
        graph = build_workflow(H3Request(prompt="x", first_frame="a.png", last_frame="b.png"))
        self.assertEqual(graph["load_first_frame"]["inputs"]["image"], "a.png")
        self.assertEqual(graph["conditioning"]["inputs"]["first_frame"], ["load_first_frame", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["last_frame"], ["load_last_frame", 0])

    def test_reference_sheets_and_frame_anchors_share_one_conditioning_chain(self):
        graph = build_workflow(H3Request(
            prompt="<Picture 1> defines the subject",
            references=("character-sheet.png", "setting-sheet.png"),
            first_frame="start.png", last_frame="end.png",
        ))
        self.assertEqual(graph["conditioning"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(
            graph["conditioning"]["inputs"]["ref_images"],
            {"ref_image_1": ["load_ref_1", 0], "ref_image_2": ["load_ref_2", 0]},
        )
        self.assertEqual(graph["guide_0"]["inputs"]["frame_idx"], 0)
        self.assertEqual(graph["guide_1"]["inputs"]["frame_idx"], -1)
        self.assertEqual(graph["guider"]["inputs"]["conditioning"], ["guide_1", 0])
        self.assertNotIn("first_frame", graph["conditioning"]["inputs"])

    def test_reference_route_rejects_more_than_nine_sheets(self):
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x", references=tuple(f"r{i}.png" for i in range(10))))

    def test_graph_references_only_nodes_it_defines(self):
        graph = build_workflow(H3Request(prompt="x", first_frame="a.png"))
        for node in graph.values():
            for value in node["inputs"].values():
                if isinstance(value, list):
                    self.assertIn(value[0], graph)

    def test_invalid_requests_are_rejected_before_reaching_the_gpu(self):
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="   "))
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x", width=1000))
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x", height=0))
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x", width=1024, height=1024))
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x", width=1080, height=1920))
        with self.assertRaises(H3RuntimeError):
            build_workflow(H3Request(prompt="x"), H3Settings(fps=30))

    def test_native_portrait_is_accepted(self):
        graph = build_workflow(H3Request(prompt="x", width=768, height=1344))
        self.assertEqual(graph["conditioning"]["inputs"]["width"], 768)
        self.assertEqual(graph["conditioning"]["inputs"]["height"], 1344)


class OutputCollectionTests(unittest.TestCase):
    def test_every_saved_file_is_collected_regardless_of_output_key(self):
        entry = {
            "outputs": {
                "save": {"images": [{"filename": "clip.mp4", "subfolder": "video", "type": "output"}]},
                "extra": {"audio": [{"filename": "track.flac", "subfolder": "", "type": "output"}], "text": ["ignored"]},
            }
        }
        self.assertEqual(
            _iter_output_files(entry),
            [("clip.mp4", "video", "output"), ("track.flac", "", "output")],
        )

    def test_missing_outputs_yield_nothing(self):
        self.assertEqual(_iter_output_files({}), [])


if __name__ == "__main__":
    unittest.main()
