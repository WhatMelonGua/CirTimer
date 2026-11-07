"""Built-in movement library: what to actually do during a break.

Text is deliberately plain "activity suggestion" wording — no medical claims.
Each entry points at a generated SVG diagram in ``assets/actions``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import project_root

SVG_DIR = project_root() / "assets" / "actions"


@dataclass(frozen=True)
class Action:
    id: str
    name: str
    area: str            # knee | hip | pelvis | back | neck | eye | breath | general
    seconds: int         # suggested duration
    detail: str          # steps
    needs_leave: bool = False
    equipment: str = ""

    @property
    def svg(self):
        p = SVG_DIR / f"{self.id}.svg"
        return p if p.is_file() else None

    @property
    def area_label(self) -> str:
        return AREA_LABELS.get(self.area, "活动")


AREA_LABELS = {
    "knee": "膝",
    "hip": "髋",
    "pelvis": "盆腔",
    "back": "腰背",
    "neck": "颈肩",
    "eye": "眼",
    "breath": "呼吸",
    "general": "通用",
}

ACTIONS: list[Action] = [
    Action("walk", "起身走动", "general", 120,
           "离开工位走动 2 分钟，能去接水、上个厕所更好。", needs_leave=True),
    Action("stand_up", "站起来", "general", 30,
           "从椅子上站起，挺直后背，双手向上伸展 10 秒。", needs_leave=True),
    Action("wall_squat", "靠墙静蹲", "knee", 90,
           "背贴墙，膝盖弯到 90°，小腿垂直地面，坚持 30 秒 ×3 组。", needs_leave=True),
    Action("seated_ext", "坐姿伸膝", "knee", 60,
           "坐直，一条腿缓慢伸直、勾脚尖，保持 5 秒，左右各 10 次。"),
    Action("leg_raise", "直腿抬高", "knee", 60,
           "坐姿，腿伸直抬高到与髋同高，停 2 秒放下，左右各 10 次。"),
    Action("hamstring", "腘绳肌拉伸", "knee", 60,
           "站立前屈，膝盖微屈，手够向脚踝，感受大腿后侧拉伸 30 秒 ×2。",
           needs_leave=True),
    Action("calf", "小腿拉伸", "knee", 45,
           "前脚掌踩在台阶边缘，脚跟下沉，保持 30 秒，左右各一次。",
           needs_leave=True),
    Action("hip_flexor", "髋屈肌拉伸", "hip", 60,
           "弓步下沉，后侧膝盖着地，骨盆前推，每侧 30 秒。", needs_leave=True),
    Action("glute", "臀部拉伸", "hip", 60,
           "坐姿，一脚踝搭在对侧膝盖上，身体前倾，每侧 30 秒。"),
    Action("bridge", "臀桥", "hip", 60,
           "仰卧屈膝，臀部抬起至肩髋膝成直线，停 2 秒，做 12 次。", needs_leave=True),
    Action("kegel", "提肛练习", "pelvis", 60,
           "吸气放松，呼气时收紧盆底肌 3 秒再放松，10 次 ×3 组。"),
    Action("breathing", "腹式呼吸", "breath", 120,
           "一手放腹部，吸气 4 秒鼓起、呼气 6 秒沉下，做 10 轮。"),
    Action("pelvic_tilt", "骨盆前后倾", "pelvis", 45,
           "坐直，骨盆缓慢前倾再后倾，幅度小而稳，做 15 次。"),
    Action("neck_side", "颈部侧屈", "neck", 30,
           "头缓慢倒向一侧，手轻压 15 秒，换边；不要绕圈。"),
    Action("shoulder_roll", "耸肩绕环", "neck", 40,
           "双肩向上耸起，向后画圈 10 次，再反方向 10 次。"),
    Action("chest_open", "胸椎伸展", "back", 40,
           "双手交握放背后，挺胸、肩胛骨内收，保持 15 秒 ×2。"),
    Action("cat_cow", "猫牛式", "back", 60,
           "四点支撑，吸气塌腰抬头、呼气拱背低头，做 10 轮。",
           needs_leave=True),
    Action("eye_2020", "20-20-20", "eye", 20,
           "看 6 米外的东西 20 秒，眨眨眼，再看屏幕。"),
    Action("eye_palm", "掌心敷眼", "eye", 30,
           "双手搓热，虚盖在闭着的眼睛上，深呼吸 30 秒。"),
]

BY_ID = {a.id: a for a in ACTIONS}


def get(action_id: str) -> Action | None:
    return BY_ID.get(action_id)


def resolve(ids: list[str] | None) -> list[Action]:
    out = []
    for aid in ids or []:
        action = BY_ID.get(aid)
        if action is not None:
            out.append(action)
    return out


def by_area(area: str) -> list[Action]:
    return [a for a in ACTIONS if a.area == area]
