"""后端运行时使用的轻量级智能体图。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple


class AgentGraph:
    """维护智能体对象和有向关注边。"""

    def __init__(self) -> None:
        self._agents: Dict[int, object] = {}
        self._edges: dict[int, set[int]] = defaultdict(set)

    def reset(self) -> None:
        self._agents.clear()
        self._edges.clear()

    def add_agent(self, agent: object) -> None:
        """把一个 agent 放入图中。"""

        agent_id = int(getattr(agent, "agent_id"))
        self._agents[agent_id] = agent
        self._edges.setdefault(agent_id, set())

    def remove_agent(self, agent: object) -> None:
        agent_id = int(getattr(agent, "agent_id"))
        self._agents.pop(agent_id, None)
        self._edges.pop(agent_id, None)
        for neighbors in self._edges.values():
            neighbors.discard(agent_id)

    def add_edge(self, agent_id_0: int, agent_id_1: int) -> None:
        """新增一条从 `agent_id_0` 指向 `agent_id_1` 的边。"""
        self._edges[int(agent_id_0)].add(int(agent_id_1))

    def remove_edge(self, agent_id_0: int, agent_id_1: int) -> None:
        self._edges.get(int(agent_id_0), set()).discard(int(agent_id_1))

    def get_agent(self, agent_id: int) -> object:
        return self._agents[int(agent_id)]

    def get_agents(self, agent_ids: Iterable[int] | None = None) -> List[Tuple[int, object]]:
        """返回指定 agent，或返回全部 agent。"""
        if agent_ids is None:
            return sorted(self._agents.items(), key=lambda item: item[0])
        return [(int(agent_id), self._agents[int(agent_id)]) for agent_id in agent_ids]

    def get_edges(self) -> list[tuple[int, int]]:
        edges: list[tuple[int, int]] = []
        for source, targets in self._edges.items():
            for target in sorted(targets):
                edges.append((source, target))
        return edges

    def get_num_nodes(self) -> int:
        return len(self._agents)

    def get_num_edges(self) -> int:
        return sum(len(targets) for targets in self._edges.values())

    def successors(self, agent_id: int) -> list[int]:
        return sorted(self._edges.get(int(agent_id), set()))

    def predecessors(self, agent_id: int) -> list[int]:
        target = int(agent_id)
        return sorted(source for source, targets in self._edges.items() if target in targets)
