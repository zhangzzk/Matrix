import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamdive.narrative_architecture import WorldExpansionPlan


class WorldExpansionPlanTests(unittest.TestCase):
    def test_new_plot_threads_accept_list_matches_source_patterns(self) -> None:
        payload = {
            "new_plot_threads": [
                {
                    "thread_id": "thread_forgotten_pact",
                    "role_in_story": "Secondary mystery that reinforces the main conflict",
                    "introduction_timing": "Early rising action",
                    "summary": "A broken pact resurfaces and complicates the protagonist's loyalties.",
                    "matches_source_patterns": [
                        "Mythological integration into personal stakes",
                        "Slow-burn revelation tied to original plot progression",
                    ],
                }
            ]
        }

        plan = WorldExpansionPlan(**payload)

        self.assertEqual(
            plan.new_plot_threads[0].matches_source_patterns,
            [
                "Mythological integration into personal stakes",
                "Slow-burn revelation tied to original plot progression",
            ],
        )


if __name__ == "__main__":
    unittest.main()
