"""环境工厂入口。
把环境构造统一收口到一个函数里。
这样调用方不需要直接实例化 ``SimulationEnv``。
"""

from Backend.environment.env import SimulationEnv


def make(*args, **kwargs) -> SimulationEnv:
    """仿照 OASIS 的 make 入口，统一创建环境对象。"""
    return SimulationEnv(*args, **kwargs)
