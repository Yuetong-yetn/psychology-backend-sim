from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationDefaults:
    """Default materials and numeric ranges for debug input generation."""

    personas: tuple[tuple[str, str, str, str], ...] = (
        ("Alex", "journalist", "moderate", "analytical"),
        ("Bea", "artist", "progressive", "expressive"),
        ("Chen", "programmer", "conservative", "direct"),
        ("Dana", "teacher", "moderate", "empathetic"),
        ("Evan", "researcher", "progressive", "measured"),
        ("Faye", "designer", "moderate", "expressive"),
        ("Gao", "engineer", "conservative", "direct"),
        ("Hana", "caregiver", "progressive", "supportive"),
        ("Ivan", "product_manager", "moderate", "balanced"),
        ("Jia", "student", "progressive", "curious"),
    )
    topics: tuple[str, ...] = (
        "city public budget adjustment",
        "new platform content moderation rules",
        "university AI teaching pilot",
        "local transit fare optimization",
        "late-night neighborhood economy expansion",
        "electric vehicle subsidy changes",
    )
    context_snippets: tuple[str, ...] = (
        "Public opinion is divided.",
        "Some users seek consensus while others amplify conflict.",
        "Posts with strong emotion receive higher visibility.",
        "Users can post, browse, reply, like, share, and influence each other.",
    )
    support_tendency_range: tuple[float, float] = (0.35, 0.75)
    threat_sensitivity_range: tuple[float, float] = (0.25, 0.7)
    self_efficacy_range: tuple[float, float] = (0.35, 0.8)
    emotion_range: tuple[float, float] = (-0.25, 0.25)
    stress_range: tuple[float, float] = (0.12, 0.55)
    expectation_range: tuple[float, float] = (0.42, 0.72)
    satisfaction_range: tuple[float, float] = (-0.08, 0.12)
    dopamine_range: tuple[float, float] = (0.42, 0.68)
    influence_range: tuple[float, float] = (0.3, 0.7)
    schema_flexibility_range: tuple[float, float] = (0.35, 0.7)
    empathy_range: tuple[float, float] = (0.4, 0.78)
    seed_post_sentiment_range: tuple[float, float] = (-0.65, 0.75)
    seed_post_extra_intensity_range: tuple[float, float] = (0.08, 0.22)
    seed_post_intensity_scale: float = 0.65
    relationship_extra_follow_probability: float = 0.35


@dataclass(frozen=True)
class EnvironmentDefaults:
    """Default settings for the environment scheduler layer."""

    llm_semaphore: int = 64
    llm_worker_threads: int = 64
    appraisal_llm_ratio: float = 0.1


@dataclass(frozen=True)
class BackendIO:
    """Default input and output file names for the backend."""

    outputs_dir_name: str = "outputs"
    examples_dir_name: str = "examples"
    viewer_html_name: str = "viewer.html"
    default_input_name: str = "backend_sample_input.json"
    default_output_name: str = "backend_sample_output.json"
    exported_snapshot_name: str = "simulation_snapshot.json"


@dataclass(frozen=True)
class AgentDynamics:
    """Default coefficients used by agent state updates."""

    contagion_weight: float = 0.18
    beta_m: float = 0.16
    emotion_valence_bias: float = 0.28
    emotion_uncertainty_bias: float = 0.22
    emotion_control_bias: float = 0.18
    contagion_threat_gain: float = 0.08
    contagion_efficacy_loss: float = 0.06
    eta: float = 0.35
    alpha_E: float = 0.25
    gamma_DA: float = 0.22
    lambda_pred: float = 0.35
    kappa_zeta: float = 0.12
    tau_epsilon: float = 0.72
    kappa_eq: float = 0.08
    eq_recovery: float = 0.02
    lambda_S: float = -0.35


GENERATION_DEFAULTS = GenerationDefaults()
ENVIRONMENT_DEFAULTS = EnvironmentDefaults()
BACKEND_IO = BackendIO()
AGENT_DYNAMICS = AgentDynamics()
