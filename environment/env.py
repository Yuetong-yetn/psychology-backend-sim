"""Async simulation environment orchestration layer."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List

from config.backend_settings import ENVIRONMENT_DEFAULTS
from environment.env_action import LLMAction, ManualAction
from environment.scenario import SimulatedScenario
from social_agent.agent import AgentRoundResult, SimulatedAgent
from social_agent.agent_graph import AgentGraph
from social_agent.agents_generator import generate_custom_agents
from social_platform.platform import Platform
from social_platform.storage import SimulationStorage

ProgressCallback = Callable[[dict[str, object]], Awaitable[None] | None]


async def _emit_progress(
    progress_callback: ProgressCallback | None,
    payload: dict[str, object],
) -> None:
    # Progress reporting is optional so the same env can be reused by CLI and
    # web callers without changing the execution flow.
    if progress_callback is None:
        return
    maybe_awaitable = progress_callback(payload)
    if maybe_awaitable is not None:
        await maybe_awaitable


@dataclass
class SimulationEnv:
    """Coordinates agents, platform, scenario, and storage for simulation runs."""

    agents: List[SimulatedAgent] | None = None
    platform: Platform = field(default_factory=Platform)
    scenario_prompt: str = ""
    scenario: SimulatedScenario | None = None
    storage: SimulationStorage | None = None
    round_index: int = 0
    history: List[dict] = field(default_factory=list)
    agent_graph: AgentGraph | None = None
    semaphore: int = ENVIRONMENT_DEFAULTS.llm_semaphore
    worker_threads: int = ENVIRONMENT_DEFAULTS.llm_worker_threads

    def __post_init__(self) -> None:
        # Normalize the relationship between the explicit agent list and the
        # graph view so later methods can rely on both being populated.
        if self.agent_graph is None:
            self.agent_graph = AgentGraph()
            for agent in self.agents or []:
                self.agent_graph.add_agent(agent)
        elif self.agents is None:
            self.agents = [agent for _, agent in self.agent_graph.get_agents()]
        else:
            existing_ids = {agent_id for agent_id, _ in self.agent_graph.get_agents()}
            for agent in self.agents:
                if agent.agent_id not in existing_ids:
                    self.agent_graph.add_agent(agent)

        self.agents = self.agents or [agent for _, agent in self.agent_graph.get_agents()]
        # The semaphore bounds concurrent agent evaluation; the thread pool runs
        # blocking cognition work without stalling the event loop.
        self._llm_semaphore = asyncio.Semaphore(self.semaphore)
        self._llm_executor = ThreadPoolExecutor(
            max_workers=max(4, self.worker_threads),
            thread_name_prefix="sim-llm",
        )
        self._platform_task: asyncio.Task | None = None

    async def areset(self) -> None:
        # Reset round counters/history, restart the platform loop if needed, and
        # re-bind each agent onto the shared runtime objects.
        self.round_index = 0
        self.history.clear()
        prompt = self._get_scenario_prompt()
        self.platform.reset(scenario_prompt=prompt)
        if self._platform_task is None or self._platform_task.done():
            self._platform_task = asyncio.create_task(self.platform.running())

        self.agent_graph = await generate_custom_agents(
            channel=self.platform.channel,
            agent_graph=self.agent_graph,
        )
        self.agents = [agent for _, agent in self.agent_graph.get_agents()]
        for _, agent in self.agent_graph.get_agents():
            agent.bind_runtime(
                channel=self.platform.channel,
                agent_graph=self.agent_graph,
                platform=self.platform,
            )
            await agent.action.register_agent(agent.profile.name)

    def _run_single_agent_round(
        self,
        agent: SimulatedAgent,
        round_index: int,
        feed: List[dict],
    ) -> AgentRoundResult:
        # This synchronous helper is what actually executes inside the worker pool.
        return agent.run_round(
            round_index=round_index,
            scenario_prompt=self._get_scenario_prompt(),
            feed=feed,
        )

    async def _dispatch_platform_action(
        self,
        agent_id: int,
        action_name: str,
        payload: dict | None = None,
    ) -> dict:
        # Low-level helper for sending one action through the platform channel.
        message_id = await self.platform.channel.write_to_receive_queue(
            (agent_id, payload or {}, action_name)
        )
        _message_id, _agent_id, result = await self.platform.channel.read_from_send_queue(message_id)
        return dict(result)

    async def _dispatch_agent_result(
        self,
        result: AgentRoundResult,
        round_index: int,
    ) -> None:
        # Replay the chosen decision from one agent back onto the shared platform.
        agent = self.agent_graph.get_agent(result.profile.agent_id)
        await agent.action.apply_decision(result.decision, round_index)

    def _finalize_round(
        self,
        round_results: Dict[int, AgentRoundResult],
        round_index: int,
    ) -> Dict[int, AgentRoundResult]:
        # Commit aggregate platform state first, then append a serialized round
        # record for later snapshot export.
        self.platform.commit_round(
            round_index=round_index,
            round_results=round_results,
        )
        self.history.append(
            {
                "round_index": round_index,
                "results": {
                    agent_id: result.to_dict()
                    for agent_id, result in round_results.items()
                },
            }
        )
        self.round_index = round_index + 1
        return round_results

    async def _perform_llm_action(
        self,
        agent: SimulatedAgent,
        round_index: int,
        feed: List[dict],
    ) -> AgentRoundResult:
        # Agent cognition is evaluated concurrently in background worker threads.
        async with self._llm_semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._llm_executor,
                self._run_single_agent_round,
                agent,
                round_index,
                feed,
            )

    async def astep(
        self,
        actions: dict[SimulatedAgent, ManualAction | LLMAction | List[ManualAction | LLMAction]] | None = None,
        *,
        progress_callback: ProgressCallback | None = None,
        round_number: int | None = None,
        total_rounds: int | None = None,
        progress_start: float | None = None,
        progress_span: float | None = None,
    ) -> Dict[int, AgentRoundResult]:
        # One round consists of:
        # 1. optional manual actions
        # 2. feed fetch
        # 3. parallel agent evaluation
        # 4. applying platform actions and committing the round
        round_index = self.round_index
        round_label = round_number if round_number is not None else round_index + 1
        total_label = total_rounds if total_rounds is not None else "?"
        base_progress = 0.15 if progress_start is None else progress_start
        span_progress = 0.75 if progress_span is None else progress_span

        def _progress(offset: float) -> float:
            return max(0.0, min(1.0, base_progress + span_progress * offset))

        if actions:
            await self._perform_manual_actions(actions)

        await _emit_progress(
            progress_callback,
            {
                "stage": "fetching_feeds",
                "completed_rounds": round_index,
                "total_rounds": total_rounds,
                "current_round": round_label,
                "completed_agents": 0,
                "total_agents": len(self.agents or []),
                "progress": _progress(0.02),
                "message": f"Round {round_label}/{total_label}: fetching agent feeds",
            },
        )
        # Each agent reads the current platform state as a personalized feed.
        feeds = await asyncio.gather(
            *(agent.environment.get_feed() for _, agent in self.agent_graph.get_agents())
        )

        agent_entries = list(self.agent_graph.get_agents())
        total_agents_count = len(agent_entries)
        await _emit_progress(
            progress_callback,
            {
                "stage": "evaluating_agents",
                "completed_rounds": round_index,
                "total_rounds": total_rounds,
                "current_round": round_label,
                "completed_agents": 0,
                "total_agents": total_agents_count,
                "progress": _progress(0.08),
                "message": f"Round {round_label}/{total_label}: evaluating agents (0/{total_agents_count})",
            },
        )

        # Launch all agent-round evaluations in parallel and collect them as
        # they finish so progress can be updated incrementally.
        tasks = [
            asyncio.create_task(self._perform_llm_action(agent, round_index, feed))
            for (_, agent), feed in zip(agent_entries, feeds)
        ]
        results: list[AgentRoundResult] = []
        completed_agents = 0
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            completed_agents += 1
            await _emit_progress(
                progress_callback,
                {
                    "stage": "evaluating_agents",
                    "completed_rounds": round_index,
                    "total_rounds": total_rounds,
                    "current_round": round_label,
                    "completed_agents": completed_agents,
                    "total_agents": total_agents_count,
                    "current_agent_id": result.profile.agent_id,
                    "current_agent_name": result.profile.name,
                    "progress": _progress(0.08 + 0.62 * (completed_agents / max(1, total_agents_count))),
                    "message": f"Round {round_label}/{total_label}: evaluating agents ({completed_agents}/{total_agents_count})",
                },
            )

        await _emit_progress(
            progress_callback,
            {
                "stage": "applying_actions",
                "completed_rounds": round_index,
                "total_rounds": total_rounds,
                "current_round": round_label,
                "completed_agents": total_agents_count,
                "total_agents": total_agents_count,
                "progress": _progress(0.78),
                "message": f"Round {round_label}/{total_label}: applying platform actions",
            },
        )
        # After all decisions are available, apply them onto the shared platform.
        await asyncio.gather(
            *(self._dispatch_agent_result(result, round_index) for result in results)
        )

        round_results = {result.profile.agent_id: result for result in results}
        await _emit_progress(
            progress_callback,
            {
                "stage": "finalizing_round",
                "completed_rounds": round_index,
                "total_rounds": total_rounds,
                "current_round": round_label,
                "completed_agents": total_agents_count,
                "total_agents": total_agents_count,
                "progress": _progress(0.92),
                "message": f"Round {round_label}/{total_label}: finalizing round state",
            },
        )
        return self._finalize_round(round_results, round_index)

    async def arun(
        self,
        rounds: int,
        progress_callback: ProgressCallback | None = None,
    ) -> List[Dict[int, AgentRoundResult]]:
        # Multi-round driver that repeatedly calls astep and emits round-level
        # progress updates around each step.
        outputs: List[Dict[int, AgentRoundResult]] = []
        for index in range(rounds):
            round_progress_start = 0.15 + (index / max(1, rounds)) * 0.75
            round_progress_span = 0.75 / max(1, rounds)
            await _emit_progress(
                progress_callback,
                {
                    "stage": "starting_round",
                    "completed_rounds": index,
                    "total_rounds": rounds,
                    "current_round": index + 1,
                    "progress": round_progress_start,
                    "message": f"Round {index + 1}/{rounds}: starting",
                },
            )
            outputs.append(
                await self.astep(
                    progress_callback=progress_callback,
                    round_number=index + 1,
                    total_rounds=rounds,
                    progress_start=round_progress_start,
                    progress_span=round_progress_span,
                )
            )
            await _emit_progress(
                progress_callback,
                {
                    "stage": "completed_round",
                    "completed_rounds": index + 1,
                    "total_rounds": rounds,
                    "current_round": index + 1,
                    "progress": round_progress_start + round_progress_span,
                    "message": f"Round {index + 1}/{rounds}: completed",
                },
            )
        return outputs

    async def _perform_manual_actions(
        self,
        actions: dict[SimulatedAgent, ManualAction | LLMAction | List[ManualAction | LLMAction]],
    ) -> None:
        # Manual actions are injected before the autonomous round begins.
        for agent, action in actions.items():
            entries = action if isinstance(action, list) else [action]
            for item in entries:
                if isinstance(item, LLMAction):
                    continue
                action_type = (
                    item.action_type.value
                    if hasattr(item.action_type, "value")
                    else str(item.action_type)
                )
                message_id = await self.platform.channel.write_to_receive_queue(
                    (agent.agent_id, dict(item.action_args), action_type)
                )
                await self.platform.channel.read_from_send_queue(message_id)

    async def aclose(self) -> None:
        # Clean shutdown for the background platform loop and worker pool.
        if self._platform_task is None:
            return
        message_id = await self.platform.channel.write_to_receive_queue((None, None, "__exit__"))
        await self.platform.channel.read_from_send_queue(message_id)
        await self._platform_task
        self._platform_task = None
        if getattr(self, "_llm_executor", None) is not None:
            self._llm_executor.shutdown(wait=True, cancel_futures=False)

    def export(self, filename: str = "simulation_snapshot.json", snapshot: dict | None = None) -> str | None:
        # Export simply serializes the current env snapshot through the storage layer.
        if self.storage is None:
            return None
        payload = snapshot if snapshot is not None else self.snapshot()
        export_path = str(self.storage.ensure_dir() / filename)
        payload["export_path"] = export_path
        return self.storage.save_json(filename, payload)

    def snapshot(self) -> dict:
        # This is the single consolidated view consumed by the frontend, debug
        # tooling, and later db persistence.
        return {
            "round_index": self.round_index,
            "scenario_prompt": self._get_scenario_prompt(),
            "scenario": self.scenario.to_dict() if self.scenario else None,
            "platform": self.platform.snapshot(),
            "agent_graph": {
                "num_nodes": self.agent_graph.get_num_nodes(),
                "num_edges": self.agent_graph.get_num_edges(),
                "edges": self.agent_graph.get_edges(),
            },
            "agents": [agent.snapshot() for _, agent in self.agent_graph.get_agents()],
            "history": self.history,
        }

    def _get_scenario_prompt(self) -> str:
        # Prefer the structured scenario prompt when a scenario object exists.
        if self.scenario is not None:
            return self.scenario.to_prompt()
        return self.scenario_prompt
