# -*- coding: utf-8 -*-
"""兼容入口：真正的几何参数表在 excavator_sim/design.py。

原来这张表躺在 tools/ 里，可是运行期也要读它 —— excavator_sim/cylinders.py
要靠 CYLINDERS 解油缸姿态，而 `ros2 run` 装出来的包只有 share/ 和 site-packages
里的 Python 包，没有 tools/。所以真身搬进包里，这里留个转发，
tools/ 下的 gen_meshes / ref_overlay / fit_boom 继续 `import design as D` 不受影响。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from excavator_sim.design import *  # noqa: E402,F401,F403
