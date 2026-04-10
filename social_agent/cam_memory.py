"""Graph-based CAM memory helpers for the social agent backend."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 1e-8:
        return [0.0 for _ in vector]
    return [item / norm for item in vector]


def _cosine_sim(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 1e-8 or right_norm <= 1e-8:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


@dataclass
class CAMNode:
    node_id: int
    round_index: int
    source: str
    content: str
    embedding: List[float]
    valence: float = 0.0
    cluster_ids: List[int] = field(default_factory=list)
    replica_of: Optional[int] = None


@dataclass
class CAMCluster:
    cluster_id: int
    node_ids: List[int] = field(default_factory=list)
    summary: str = ""
    centroid: List[float] = field(default_factory=list)


@dataclass
class CAMMemoryGraph:
    semantic_weight: float = 0.72
    time_sigma: float = 3.0
    neighbor_threshold: float = 0.7
    summary_event_limit: int = 3
    nodes: Dict[int, CAMNode] = field(default_factory=dict)
    edges: Dict[int, Set[int]] = field(default_factory=dict)
    clusters: Dict[int, CAMCluster] = field(default_factory=dict)
    _next_node_id: int = 1
    _next_cluster_id: int = 1

    def best_match(self, embedding: List[float], round_index: int) -> Dict[str, object]:
        scores = []
        for node in self.nodes.values():
            score = self._similarity(node.embedding, embedding, node.round_index, round_index)
            scores.append((node.node_id, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        candidates = [node_id for node_id, score in scores if score >= self.neighbor_threshold]
        best_similarity = scores[0][1] if scores else 0.0
        return {
            "best_similarity": _clamp(best_similarity),
            "candidates": candidates,
            "scores": scores[:6],
        }

    def add_event(
        self,
        *,
        round_index: int,
        source: str,
        content: str,
        embedding: List[float],
        valence: float,
        conflict_penalty: float,
    ) -> Dict[str, object]:
        match = self.best_match(embedding, round_index)
        candidate_ids = list(match["candidates"])
        node_id = self._add_node(
            round_index=round_index,
            source=source,
            content=content,
            embedding=embedding,
            valence=valence,
        )

        accommodated = not candidate_ids
        for candidate_id in candidate_ids:
            self._add_edge(node_id, candidate_id)

        replicated_ids = self._replicate_bridge_node(node_id)
        updated_cluster_ids = self._recompute_clusters()

        return {
            "node_id": node_id,
            "candidate_ids": candidate_ids,
            "accommodated": accommodated,
            "replicated_ids": replicated_ids,
            "updated_cluster_ids": updated_cluster_ids,
            "best_similarity": match["best_similarity"],
            "semantic_similarity": match["best_similarity"],
            "conflict_delta": -conflict_penalty if accommodated else 0.0,
        }

    def global_embedding(self) -> List[float]:
        if not self.nodes:
            return []
        dim = len(next(iter(self.nodes.values())).embedding)
        total = [0.0] * dim
        for node in self.nodes.values():
            for index, value in enumerate(node.embedding):
                total[index] += value
        avg = [value / max(1, len(self.nodes)) for value in total]
        return _normalize(avg)

    def cluster_summary_for_node(self, node_id: int) -> List[str]:
        node = self.nodes.get(node_id)
        if node is None:
            return []
        summaries = []
        for cluster_id in node.cluster_ids:
            cluster = self.clusters.get(cluster_id)
            if cluster and cluster.summary:
                summaries.append(cluster.summary)
        return summaries

    def to_dict(self) -> Dict[str, object]:
        return {
            "semantic_weight": self.semantic_weight,
            "time_sigma": self.time_sigma,
            "neighbor_threshold": self.neighbor_threshold,
            "nodes": [asdict(node) for node in self.nodes.values()],
            "edges": {str(node_id): sorted(list(neighbors)) for node_id, neighbors in self.edges.items()},
            "clusters": [asdict(cluster) for cluster in self.clusters.values()],
        }

    def _add_node(
        self,
        *,
        round_index: int,
        source: str,
        content: str,
        embedding: List[float],
        valence: float,
        replica_of: Optional[int] = None,
    ) -> int:
        node_id = self._next_node_id
        self._next_node_id += 1
        self.nodes[node_id] = CAMNode(
            node_id=node_id,
            round_index=round_index,
            source=source,
            content=content,
            embedding=list(embedding),
            valence=valence,
            replica_of=replica_of,
        )
        self.edges.setdefault(node_id, set())
        return node_id

    def _add_edge(self, left: int, right: int) -> None:
        if left == right:
            return
        self.edges.setdefault(left, set()).add(right)
        self.edges.setdefault(right, set()).add(left)

    def _similarity(
        self,
        left_embedding: List[float],
        right_embedding: List[float],
        left_round: int,
        right_round: int,
    ) -> float:
        semantic = _cosine_sim(left_embedding, right_embedding)
        time_gap = abs(left_round - right_round)
        temporal = math.exp(-((time_gap ** 2) / (2 * (self.time_sigma ** 2))))
        return _clamp(self.semantic_weight * semantic + (1 - self.semantic_weight) * temporal)

    def _replicate_bridge_node(self, node_id: int) -> List[int]:
        neighbors = list(self.edges.get(node_id, set()))
        if len(neighbors) < 2:
            return []

        components = self._components_without_node(neighbors, excluded=node_id)
        if len(components) <= 1:
            return []

        original = self.nodes[node_id]
        replicated_ids: List[int] = []
        for component in components[1:]:
            replica_id = self._add_node(
                round_index=original.round_index,
                source=original.source,
                content=original.content,
                embedding=original.embedding,
                valence=original.valence,
                replica_of=original.node_id,
            )
            for neighbor_id in component:
                self._add_edge(replica_id, neighbor_id)
            replicated_ids.append(replica_id)
        return replicated_ids

    def _components_without_node(self, candidate_nodes: List[int], excluded: int) -> List[List[int]]:
        remaining = set(candidate_nodes)
        components: List[List[int]] = []
        while remaining:
            start = remaining.pop()
            queue = [start]
            component = [start]
            while queue:
                current = queue.pop()
                for neighbor in self.edges.get(current, set()):
                    if neighbor == excluded or neighbor not in remaining:
                        continue
                    remaining.remove(neighbor)
                    queue.append(neighbor)
                    component.append(neighbor)
            components.append(sorted(component))
        return components

    def _recompute_clusters(self) -> List[int]:
        self.clusters.clear()
        visited: Set[int] = set()
        updated: List[int] = []
        for node_id in sorted(self.nodes):
            if node_id in visited:
                continue
            component = []
            queue = [node_id]
            visited.add(node_id)
            while queue:
                current = queue.pop()
                component.append(current)
                for neighbor in self.edges.get(current, set()):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    queue.append(neighbor)

            cluster_id = self._next_cluster_id
            self._next_cluster_id += 1
            centroid = self._cluster_centroid(component)
            summary = self._summarize_component(component)
            self.clusters[cluster_id] = CAMCluster(
                cluster_id=cluster_id,
                node_ids=sorted(component),
                summary=summary,
                centroid=centroid,
            )
            for component_node_id in component:
                self.nodes[component_node_id].cluster_ids = [cluster_id]
            updated.append(cluster_id)
        return updated

    def _cluster_centroid(self, node_ids: List[int]) -> List[float]:
        if not node_ids:
            return []
        dim = len(self.nodes[node_ids[0]].embedding)
        total = [0.0] * dim
        for node_id in node_ids:
            for index, value in enumerate(self.nodes[node_id].embedding):
                total[index] += value
        return _normalize([value / max(1, len(node_ids)) for value in total])

    def _summarize_component(self, node_ids: List[int]) -> str:
        ordered_nodes = sorted(
            (self.nodes[node_id] for node_id in node_ids),
            key=lambda item: (item.round_index, item.node_id),
            reverse=True,
        )
        snippets = []
        for node in ordered_nodes[: self.summary_event_limit]:
            text = node.content.strip().replace("\n", " ")
            if len(text) > 64:
                text = text[:64] + "..."
            snippets.append(text)
        return " | ".join(snippets)
