import json
import os
import re
import networkx as nx
from typing import List, Dict, Optional, Tuple

GRAPH_DIR = os.path.join(os.path.dirname(__file__), "data", "knowledge_graphs")


def _normalize_subject_name(subject: str) -> str:
    """Normalize UI/backend topic strings to canonical KG subject names."""
    raw = (subject or "").strip()
    if not raw:
        return "math"

    # Handle composite paths like "Math/Algebra".
    if "/" in raw:
        raw = raw.split("/")[0].strip()

    # Remove grade suffixes/prefixes from selected bookshelf topics.
    # Examples: "Math 7", "Science Grade 5", "History grade-8".
    raw = re.sub(r"\bgrade[_\-\s]*\d+\b", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"\s+\d+\s*$", "", raw).strip()

    # Normalize separators.
    normalized = re.sub(r"[\s\-]+", "_", raw).strip("_").lower()
    if not normalized:
        normalized = "math"
    return normalized

class KnowledgeGraph:
    def __init__(self, subject: str, state: str = "NH"):
        self.subject = subject
        self.state = state
        self.graph = nx.DiGraph()
        self.load_graph()
        
    def load_graph(self):
        # Map legacy names to new directories
        subject_map = {
            "math": "Math",
            "english": "ELA",
            "history": "Social_Studies",
            "science": "Science",
            "social_studies": "Social_Studies",
            "ela": "ELA"
        }

        normalized_subject = _normalize_subject_name(self.subject)
        dir_name = subject_map.get(
            normalized_subject,
            normalized_subject.replace("_", " ").title().replace(" ", "_")
        )
        # Updated path: knowledge_graphs/{State}/{Subject}
        subject_dir = os.path.join(GRAPH_DIR, self.state, dir_name)
        
        if not os.path.exists(subject_dir):
            print(f"Warning: KG directory not found: {subject_dir}")
            return

        # Load all JSONs in directory
        files = sorted([f for f in os.listdir(subject_dir) if f.endswith(".json")])
        print(f"Loading {self.subject} graph ({self.state}) from {len(files)} files in {subject_dir}...")
        
        for fname in files:
            path = os.path.join(subject_dir, fname)
            self._load_single_file(path)

    def _load_single_file(self, path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                
            if "taxonomy" in data:
                 self._parse_taxonomy(data["taxonomy"])
            elif "nodes" in data:
                 self._parse_flat_list(data["nodes"])
            else:
                 # Fallback/Empty
                 pass
                 
        except Exception as e:
            print(f"Error loading KG file {path}: {e}")
            import traceback
            traceback.print_exc()

    def _parse_flat_list(self, nodes: List[Dict]):
        # Backward compatibility for Science/History until refactored
        for n_data in nodes:
            self.graph.add_node(
                n_data["id"], 
                label=n_data["label"], 
                grade_level=n_data.get("grade_level", 0),
                description=n_data.get("description", ""),
                type="concept"
            )
            for p in n_data.get("prerequisites", []):
                self.graph.add_edge(p, n_data["id"])

    def _parse_taxonomy(self, taxonomy: Dict, parent_id: str = ""):
                self._parse_taxonomy(value["subtopics"], current_id)

    def _parse_taxonomy(self, taxonomy, parent_id=None):
        # Recursively parse nested dictionary
        # parent_id example: "Arithmetic->Number_Sense"
        
        for key, value in taxonomy.items():
            # Current node ID
            current_id = f"{parent_id}->{key}" if parent_id else key
            current_id = current_id.replace(" ", "_") # Normalize ID to avoid spaces
            
            # Attributes
            grade = value.get("grade_level", 0)
            node_type = value.get("type", "core")
            
            # Check if this is a leaf node (Concept) or a Branch (Category)
            if "concepts" in value:
                # It's a Subtopic with concepts
                self.graph.add_node(current_id, label=key, type="subtopic", grade_level=grade, node_type=node_type)
                if parent_id:
                    self.graph.add_edge(parent_id, current_id)
                
                # Add Concepts
                prev_concept_id = None
                for concept in value["concepts"]:
                    label = concept["label"]
                    concept_grade = concept.get("grade_level", grade) # Inherit grade if not set
                    concept_type = concept.get("type", node_type) # Inherit type
                    desc = concept.get("description", "")
                    
                    concept_id = f"{current_id}->{label}".replace(" ", "_")
                    
                    self.graph.add_node(
                        concept_id, 
                        label=label, 
                        grade_level=concept_grade, 
                        description=desc,
                        type="concept",
                        node_type=concept_type
                    )
                    
                    # Edges: Parent -> Concept
                    self.graph.add_edge(current_id, concept_id)
                    
                    # Edges: Sequential Prerequisite (within list)
                    # ONLY enforce strict sequence for CORE types
                    if prev_concept_id and concept_type == "core":
                        self.graph.add_edge(prev_concept_id, concept_id)
                    
                    prev_concept_id = concept_id
                    
            elif "subtopics" in value:
                # It's a Subject/Topic with subtopics
                self.graph.add_node(current_id, label=key, type="topic", grade_level=grade, node_type=node_type)
                if parent_id:
                    self.graph.add_edge(parent_id, current_id)
                
                self._parse_taxonomy(value["subtopics"], current_id)
            else:
                 # Fallback?
                 pass

    def get_next_learnable_nodes(self, completed_nodes: List[str], target_grade: int = None) -> List[Dict]:
        """Returns concept nodes where all prerequisites are met."""
        candidates = []
        
        # We process ALL nodes, but filter for 'concept' type generally? 
        # Or maybe we teach topics too? For now, focus on 'concept' type (leafs)
        
        for node in self.graph.nodes():
            if node in completed_nodes:
                continue
            
            # Filter: Only suggest 'concept' nodes for specific problems
            # Use 'type' attribute
            if self.graph.nodes[node].get("type") != "concept":
                continue

            # Check Prerequisites (incoming edges)
            # We treat ALL incoming edges as prerequisites
            # EXCEPTION: The edge from the Parent (Topic) is structural, not a prereq for *learning* per se?
            # Actually, usually you must unlock the Topic (Parent) to learn the Concept.
            # But the Parent is "completed" when... any child is? or all?
            # Let's simplify: Prerequisites are ONLY other 'concept' nodes.
            
            prereqs_met = True
            for predecessor in self.graph.predecessors(node):
                start_node = self.graph.nodes[predecessor]
                if start_node.get("type") == "concept":
                    if predecessor not in completed_nodes:
                        prereqs_met = False
                        break
            
            if prereqs_met:
                candidates.append(self.get_node(node))
                
        # Sort by grade level, then ID
        if target_grade is not None:
             # Prioritize nodes closest to the target grade
             # Sort Key: (Distance from Target, Grade Level (lower is easier), ID)
             candidates.sort(key=lambda x: (abs(x.grade_level - target_grade), x.grade_level, x.id))
        else:
             candidates.sort(key=lambda x: (x.grade_level, x.id))
             
        return candidates

    def get_prerequisites(self, node_id: str) -> List[str]:
        """Returns a list of IDs of immediate prerequisites (concept predecessors)."""
        if node_id not in self.graph:
            return []
            
        prereqs = []
        for predecessor in self.graph.predecessors(node_id):
            node = self.graph.nodes[predecessor]
            # Only count distinct concepts as learning prereqs, not structural parents?
            # Actually, `_parse_flat_list` adds explicit prereqs. 
            # `_parse_taxonomy` adds Parent->Child edges and Sequence edges.
            # If we struggle with "Equality", we should review previous concept "Comparisons" (if sequential) 
            # OR parent "Number_Sense"?
            # Let's return ALL concept predecessors.
            if node.get("type") == "concept":
                prereqs.append(predecessor)
        return prereqs

    def get_node(self, node_id: str) -> Optional[object]:
        if node_id not in self.graph:
            return None
        # Return a simple object-like struct for compatibility
        data = self.graph.nodes[node_id]
        
        class NodeObj:
            def __init__(self, id, data):
                self.id = id
                self.label = data.get("label", id)
                self.description = data.get("description", "")
                self.grade_level = data.get("grade_level", 0)
                
        return NodeObj(node_id, data)

    def get_window(self, focus_node_id: str = None, window_size: int = 20) -> List[object]:
        """Returns a list of nodes centered around focus_node_id (sorted by sequence)."""
        # 1. Get All Concept Nodes sorted by "Curriculum Order"
        # Sort Key: (Grade, ID) - simplest heuristic for now.
        # Ideally we traverse the edges, but DAG linearization is complex.
        # Grade-level grouping is safer for display.
        
        all_concepts = []
        for n in self.graph.nodes():
            data = self.graph.nodes[n]
            # Include Topics and Subtopics or just Concepts?
            # User said "10 previous/10 following nodes". Usually implies linear list of items.
            # Let's include everything but sorted.
            all_concepts.append(self.get_node(n))
            
        # Sort
        all_concepts.sort(key=lambda x: (x.grade_level, x.id))
        
        # 2. Find Index
        idx = 0
        if focus_node_id:
            for i, n in enumerate(all_concepts):
                if n.id == focus_node_id:
                    idx = i
                    break
        
        # 3. Slice
        half = window_size // 2
        start = max(0, idx - half)
        end = min(len(all_concepts), idx + half + 1)
        
        # Adjust if at bounds to try to fill window?
        # e.g. if start is 0, extend end.
        if start == 0:
            end = min(len(all_concepts), window_size)
        if end == len(all_concepts):
            start = max(0, len(all_concepts) - window_size)
            
        return all_concepts[start:end]

    def get_completion_stats(self, completed_nodes: List[str], subtree_root: str = None):
        # Count only 'concept' nodes regarding standard curriculum (CORE)
        # Recommended/Elective nodes do not count towards Mastery %
        
        candidates = self.graph.nodes()
        if subtree_root:
             candidates = [n for n in candidates if n.startswith(subtree_root)]
             
        concepts = [
            n for n in candidates 
            if self.graph.nodes[n].get("type") == "concept" and self.graph.nodes[n].get("node_type") == "core"
        ]
        total = len(concepts)
        if total == 0:
            return 0, 0
            
        done = len([
            n for n in completed_nodes 
            if n in self.graph 
            and (not subtree_root or n.startswith(subtree_root))
            and self.graph.nodes[n].get("type") == "concept" 
            and self.graph.nodes[n].get("node_type") == "core"
        ])
        return done, total

# Singleton/Factory mapping
_graphs = {}

def get_graph(subject: str, state: str = "NH") -> KnowledgeGraph:
    normalized_subject = _normalize_subject_name(subject)
    cache_key = f"{state}:{normalized_subject}"
    
    if cache_key not in _graphs:
        _graphs[cache_key] = KnowledgeGraph(normalized_subject, state)
    return _graphs[cache_key]

def get_all_subjects_stats(player_id: int, db_session) -> Tuple[int, int]:
    """
    Calculates the total completed core concepts vs total available core concepts
    across ALL subjects (Math, Science, History, English) for a given player.
    """
    subjects = ["Math", "Science", "Social_Studies", "ELA"]
    total_done = 0
    total_concepts = 0
    
    from .database import TopicProgress # Import locally to avoid circular dep if needed
    
    for subj in subjects:
        # Load Graph
        kg = get_graph(subj)
        if not kg or len(kg.graph.nodes) == 0:
            continue
            
        # Get Player Progress for this subject
        # Note: TopicProgress usually stores "Math", "Science" etc.
        db_topic_name = subj

        
        prog = db_session.query(TopicProgress).filter(
            TopicProgress.player_id == player_id,
            TopicProgress.topic_name == db_topic_name
        ).first()
        
        completed = []
        if prog and prog.completed_nodes:
            completed = prog.completed_nodes
            
        done, total = kg.get_completion_stats(completed)
        total_done += done
        total_concepts += total
        
    return total_done, total_concepts
