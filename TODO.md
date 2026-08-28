# 待办

## 膳食纤维改用训记的数（等接口）

App 里看得到纤维，Open API 不返回。查过 2026-08-20 至 08-27 的 85 条食物记录，
`ntr` 只有 `cal` / `carb` / `fat` / `protein`，`limits` 只有 `fat` / `carb` /
`water` / `protein`，没有任何纤维字段——不是个别记录缺失，是接口整个没开。

所以现在导出里 `fiber_g` 恒为 0、`net_carbs_g` 直接等于总碳水，净碳水实际上
偏高。等训记把字段开出来再接。

要改的地方：
- `scripts/sync_xunji_recent.py` 的 `_nutrition()` 与 `daily_log` 组装处
- 两处写死的说明文字「膳食纤维暂按 0 g；净碳水按总碳水计算」
- `review` 里那条「用户确认纤维按 0 g、净碳水等于总碳水」

复查接口有没有加字段：

```
uv run python -c "
import json, sys; sys.path.insert(0, 'scripts')
from sync_xunji_recent import _post, FOOD_URL, _key, _load_env_file
_load_env_file()
r = _post(FOOD_URL, _key('XUNJI_FOOD_API_KEY'),
          {'start_date': '2026-08-27', 'end_date': '2026-08-27', 'include_detail': True})
print(sorted({k for d in r['res']['days'] for f in d['foods']['records']
              for k in (f.get('ntr') or {})}))
"
```

## 训记 App 的力量消耗只能手抄

Open API 不给。课次 note 里的 `calorie:N` 看着像训记的估算，实际是苹果健康
训练时段的消耗，三条证据：8/20、8/24、8/25、8/28 是空的（有完整组数据，
模型不会算不出来）；8/26 note 是 812 而 App 显示 572；8/27 隔夜从 42 变 43。
脚本记为 `apple_health_workout_kcal`，只存不用。

要自动化就得等训记把 App 那个数开进接口。

## 进步曲线只有重量一种轴

面板画的是最重组 + 容量，两者都要重量，所以只有重量数据的动作才进选项。
被挡在外面但确实在进步的有：

- `平板支撑_计时`（6 次 18 组，只有时长）
- `下斜卷腹`（4 次 12 组，只有次数）
- `快走`（8 次 11 组，只有时长和距离）

要看这几个的进步，得给面板加一条按时长/次数的轴，或者单独做一个自重与计时
动作的面板。`庭院劳作` 不在此列——它那一组四个字段全空，本来就没有数据。
