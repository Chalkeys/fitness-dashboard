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

## 训记自身的力量消耗模型还没见过样本

8/26 及以前 note 里的 `calorie:` 全是苹果健康导入的；同步关掉后第一条
（8/27 的 42 kcal）是残留。`xunji_active_energy` 的物理下限只挡得住不可能的
值，挡不住「可能但错」的残留。真出现非零 note 的那天，先在 App 里对一眼再入库。
