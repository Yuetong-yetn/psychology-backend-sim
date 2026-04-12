"""环境工厂入口。

把 `SimulationEnv` 的构造统一收口到一个函数，
便于外部脚本保持和 Gym/OASIS 类似的调用方式。
"""

from environment.env import SimulationEnv


def make(*args, **kwargs) -> SimulationEnv:
    """按约定创建一个仿真环境实例。"""

    return SimulationEnv(*args, **kwargs)
