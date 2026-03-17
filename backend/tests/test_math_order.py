import os
import sys
import unittest

import networkx as nx

# Add backend directory
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from knowledge_graph import KnowledgeGraph


class TestMathOrder(unittest.TestCase):
    def test_measurement_sequence(self):
        kg = KnowledgeGraph("math")

        first_id = "MD->2MDA->2.MD.1"
        second_id = "MD->2MDA->2.MD.2"

        self.assertIsNotNone(kg.get_node(first_id), "2.MD.1 node not found")
        self.assertIsNotNone(kg.get_node(second_id), "2.MD.2 node not found")

        self.assertTrue(
            nx.has_path(kg.graph, first_id, second_id),
            "2.MD.1 should be a prerequisite for 2.MD.2",
        )

        candidates = kg.get_next_learnable_nodes([], target_grade=2)
        candidate_ids = [c.id for c in candidates]

        self.assertIn(first_id, candidate_ids)
        self.assertNotIn(
            second_id,
            candidate_ids,
            "2.MD.2 should not be learnable before 2.MD.1 is completed",
        )

        unlocked_candidates = kg.get_next_learnable_nodes([first_id], target_grade=2)
        unlocked_candidate_ids = [c.id for c in unlocked_candidates]
        self.assertIn(
            second_id,
            unlocked_candidate_ids,
            "2.MD.2 should become learnable after 2.MD.1 is completed",
        )


if __name__ == "__main__":
    unittest.main()
