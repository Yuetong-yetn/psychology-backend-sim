from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationDefaults:
    """生成调试输入时使用的默认素材与数值范围。"""

    personas: tuple[tuple[str, str, str, str], ...] = (  # 名字、职业、立场、表达风格
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
    topics: tuple[str, ...] = (  # 用来随机生成仿真议题
        "城市公共预算调整",
        "平台内容审核新规",
        "高校 AI 教学试点",
        "本地交通票价优化",
        "社区夜间经济开放",
        "新能源车补贴变化",
    )
    context_snippets: tuple[str, ...] = (
        "Public opinion is divided.",
        "Some users seek consensus while others amplify conflict.",
        "Posts with strong emotion receive higher visibility.",
        "Users can post, browse, reply, like, share, and influence each other.",
    )
    support_tendency_range: tuple[float, float] = (0.35, 0.75)  # 对支持/合作线索的默认敏感区间
    threat_sensitivity_range: tuple[float, float] = (0.25, 0.7)  # 对风险/威胁线索的默认敏感区间
    self_efficacy_range: tuple[float, float] = (0.35, 0.8)  # 自我效能初值区间
    emotion_range: tuple[float, float] = (-0.25, 0.25)  # 初始情绪标量区间
    stress_range: tuple[float, float] = (0.12, 0.55)  # 初始压力区间
    expectation_range: tuple[float, float] = (0.42, 0.72)  # 初始预期区间
    satisfaction_range: tuple[float, float] = (-0.08, 0.12)  # 初始满意度区间
    dopamine_range: tuple[float, float] = (0.42, 0.68)  # 初始多巴胺水平区间
    influence_range: tuple[float, float] = (0.3, 0.7)  # 初始社会影响力区间
    schema_flexibility_range: tuple[float, float] = (0.35, 0.7)  # 图式可塑性区间
    empathy_range: tuple[float, float] = (0.4, 0.78)  # 共情水平区间
    seed_post_sentiment_range: tuple[float, float] = (-0.65, 0.75)  # 种子帖情感极性区间
    seed_post_extra_intensity_range: tuple[float, float] = (0.08, 0.22)  # 额外情绪强度扰动
    seed_post_intensity_scale: float = 0.65  # 由情感极性映射到强度时的缩放系数
    relationship_extra_follow_probability: float = 0.35  # 除环形关注外再补一条边的概率


@dataclass(frozen=True)
class EnvironmentDefaults:
    """环境调度层的默认配置。"""

    llm_semaphore: int = 32  # 并发执行 agent 轮次推理时的上限


@dataclass(frozen=True)
class BackendIO:
    """后端输入输出相关的默认文件名。"""

    outputs_dir_name: str = "outputs"
    examples_dir_name: str = "examples"
    viewer_html_name: str = "viewer.html"
    default_input_name: str = "backend_sample_input.json"
    default_output_name: str = "backend_sample_output.json"
    exported_snapshot_name: str = "simulation_snapshot.json"


@dataclass(frozen=True)
class AgentDynamics:
    """Agent 心理更新公式中使用的默认系数。"""

    contagion_weight: float = 0.18  # 外部情绪感染对当前状态的总体权重
    beta_m: float = 0.16  # 记忆/图式相关项对更新的混合系数
    emotion_valence_bias: float = 0.28  # appraisal 价性对情绪更新的影响权重
    emotion_uncertainty_bias: float = 0.22  # 不确定性对情绪扰动的放大权重
    emotion_control_bias: float = 0.18  # 控制感对情绪稳定化的权重
    contagion_threat_gain: float = 0.08  # 感染到负面内容时对威胁感的增益
    contagion_efficacy_loss: float = 0.06  # 感染到负面内容时对效能感的损失
    eta: float = 0.35  # 图式更新步长
    alpha_E: float = 0.25  # 情绪状态向平衡点回拉时的基础系数
    gamma_DA: float = 0.22  # 多巴胺相关误差对状态修正的权重
    lambda_pred: float = 0.35  # 表现预测误差的混合系数
    kappa_zeta: float = 0.12  # 目标相关信号 zeta 的更新强度
    tau_epsilon: float = 0.72  # 不可预测性 epsilon 的时间衰减系数
    kappa_eq: float = 0.08  # 平衡指数 `equilibrium` 的调整步长
    eq_recovery: float = 0.02  # 平衡状态每轮自然恢复量
    lambda_S: float = -0.35  # 压力项对满意度/稳定性的负向耦合系数


GENERATION_DEFAULTS = GenerationDefaults()
ENVIRONMENT_DEFAULTS = EnvironmentDefaults()
BACKEND_IO = BackendIO()
AGENT_DYNAMICS = AgentDynamics()
