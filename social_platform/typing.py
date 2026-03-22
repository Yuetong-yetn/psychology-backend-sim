"""平台层公共类型。

这里集中定义平台动作枚举，方便 environment 和 agent 共享一套动作语义。
"""

from enum import Enum


class ActionType(str, Enum):
    """最小互动动作集合。"""

    BROWSE_FEED = "browse_feed"
    CREATE_POST = "create_post"
    REPLY_POST = "reply_post"
    LIKE_POST = "like_post"
    SHARE_POST = "share_post"
    APPLY_INFLUENCE = "apply_influence"
    DO_NOTHING = "do_nothing"
