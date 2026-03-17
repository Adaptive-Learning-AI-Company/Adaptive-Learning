
import sys
import os
import unittest
from unittest.mock import MagicMock

# Add backend directory
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Fix imports by mocking or sys.path hacks if needed
try:
    from backend.graph import teacher_node
    from backend.knowledge_graph import KnowledgeGraph
except ImportError:
    # Try local import if run from root
    from graph import teacher_node
    from knowledge_graph import KnowledgeGraph

class TestAgentGrade(unittest.TestCase):
    def test_stale_node_override(self):
        # Scenario: DB has "Printing_Letters" (G0) as current_node.
        # Student is G2. Mastery is 0.
        # Expected: Agent checks node, sees G0 << G2, re-selects "Multiple_Meaning_Words" (G2).
        
        # We need to Mock the DB/Player/Progress in teacher_node.
        # Since that's hard to mock given the current import structure,
        # we can unit-test the LOGIC if we extract it, 
        # or we rely on the fact that we will implement the logic such that:
        # IF current_node.grade is mismatched AND mastery is 0 -> Recalculate.
        
        # For this test, let's verify that the logic I PLAN to write works 
        # using the KG directly + manual check? 
        
        # No, I want to confirm teacher_node behavior.
        # To do that without DB, I might need to mock get_db or SessionLocal.
        pass
        
    def test_teacher_node_selection(self):
        # Mock State
        state = {
            "topic": "English",
            "grade_level": "Grade 2",
            "username": "TestUser",
            "messages": [],
            "mastery": 0
        }
        
        # Parsing Check
        g_str = state.get("grade_level", "")
        target_grade = None
        if isinstance(g_str, int):
            target_grade = g_str
        elif "Grade" in str(g_str):
            import re
            m = re.search(r'\d+', str(g_str))
            if m: target_grade = int(m.group())
            
        print(f"Parsed Grade: {target_grade}")
        self.assertEqual(target_grade, 2)

        kg = KnowledgeGraph("english")
        
        # Pick any kindergarten-level concept from the current standards graph to
        # simulate a stale node for a Grade 2 student.
        stale_node_id = next(
            (
                node_id
                for node_id, data in kg.graph.nodes(data=True)
                if data.get("type") == "concept" and data.get("grade_level") == 0
            ),
            None,
        )
        curr_node = kg.get_node(stale_node_id)
        self.assertIsNotNone(curr_node)
        print(f"Current Stale Node: {curr_node.label} (G{curr_node.grade_level})")
        
        # Logic to be implemented:
        # if abs(curr.grade - target) > 1 and mastery == 0: re-select
        
        should_reselect = False
        if curr_node and target_grade is not None:
            if abs(curr_node.grade_level - target_grade) > 1: # Strict check?
                should_reselect = True
                print(">> Detected Stale Node! Triggering re-selection.")
                
        self.assertTrue(should_reselect, "Logic failed to flag G0 node as stale for G2 student")
        
        if should_reselect:
            candidates = kg.get_next_learnable_nodes([], target_grade=target_grade)
            self.assertTrue(candidates)
            print(f"Re-selected: {candidates[0].label} (G{candidates[0].grade_level})")
            self.assertEqual(candidates[0].grade_level, 2)
            self.assertNotEqual(candidates[0].id, curr_node.id)

if __name__ == '__main__':
    unittest.main()
