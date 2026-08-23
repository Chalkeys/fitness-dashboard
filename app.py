"""Streamlit entry point for the fitness dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts

from dashboard import body_figure, data, echarts_charts as ec, energy, settings
from dashboard.format import summarize_sets
from dashboard.theme import CM_TO_IN, G_TO_OZ, KG_TO_LB, classify_training

st.set_page_config(
    page_title="Fitness Dashboard",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2.2rem; max-width: 72rem;}

[data-testid="stMetric"] {
    background: #fcfcfb;
    border: 1px solid rgba(11, 11, 11, 0.10);
    border-radius: 12px;
    padding: 1rem 1.2rem;
}
[data-testid="stMetricLabel"] {color: #52514e;}
[data-testid="stMetricValue"] {color: #0b0b0b; font-size: 1.7rem;}

h1, h2, h3 {color: #0b0b0b;}
</style>
"""

RANGE_OPTIONS = {"近 30 天": 30, "近 90 天": 90, "全部": None}


def _init_settings() -> None:
    """Seed widget state from the settings file, once per session.

    Seeding the keys the widgets use means each widget adopts the stored value
    without being passed one, and later reruns leave the user's choice alone.
    """
    if st.session_state.get("_settings_loaded"):
        return
    for key, value in settings.load().items():
        st.session_state.setdefault(key, value)
    st.session_state["_settings_loaded"] = True


def _persist_settings() -> None:
    """Write the tunables back out whenever one of them changed."""
    current = {k: st.session_state.get(k, v) for k, v in settings.DEFAULTS.items()}
    if current != st.session_state.get("_settings_saved"):
        settings.save(current)
        st.session_state["_settings_saved"] = current


MEAL_ORDER = [
    "breakfast",
    "morning",
    "preworkout",
    "noon",
    "noon-added",
    "postworkout",
    "snack",
    "night",
]
MEAL_LABELS = {
    "breakfast": "早餐",
    "morning": "上午",
    "preworkout": "练前",
    "noon": "午餐",
    "noon-added": "午餐加餐",
    "postworkout": "练后",
    "snack": "加餐",
    "night": "晚餐",
}


def _sidebar_range() -> int | None:
    with st.sidebar:
        st.markdown("### 时间范围")
        label = st.radio(
            "时间范围",
            list(RANGE_OPTIONS),
            index=1,
            label_visibility="collapsed",
        )
    return RANGE_OPTIONS[label]


def _unit_toggle(page_key: str, default: str = "公制") -> bool:
    """Per-page metric/imperial switch. Returns True when imperial."""
    choice = st.segmented_control(
        "单位",
        ["公制", "英制"],
        default=default,
        key=f"units_{page_key}",
        label_visibility="collapsed",
    )
    return choice == "英制"


def _delta(series: pd.Series, days: int) -> float | None:
    """Change of the latest value vs. the closest value ~days earlier."""
    s = series.dropna()
    if len(s) < 2:
        return None
    latest_ts = s.index.max()
    earlier = s[s.index <= latest_ts - pd.Timedelta(days=days)]
    if earlier.empty:
        earlier = s.iloc[[0]]
    return float(s.iloc[-1] - earlier.iloc[-1])


# --- Pages -----------------------------------------------------------------


def page_overview() -> None:
    st.title("概览")
    imperial = _unit_toggle("overview")

    daily = data.load_daily_logs()
    body = data.load_body_measurements()
    sessions = data.load_workout_sessions()

    if daily.empty and body.empty:
        st.info("数据库还没有数据，先运行导入脚本。")
        return

    weight = body.set_index("measured_at")["weight_kg"]
    latest_weight = weight.dropna().iloc[-1] if not weight.dropna().empty else None
    weight_d7 = _delta(weight, 7)

    recent7 = data.filter_by_range(daily, "log_date", 7)
    fed7 = recent7[recent7["tdee"] > 0]
    # The card and the chart below show the same quantity, so they share a mode.
    corrected = st.session_state.get("balance_mode", settings.DEFAULTS["balance_mode"]) == "纠偏后"
    card_bias = _bias_factors() if corrected else (0.0, 0.0, energy.DEFAULT_BMR)
    avg_balance = (
        energy.corrected_balance(recent7, *card_bias).mean() if not fed7.empty else None
    )
    avg_protein = fed7["protein_g"].mean() if not fed7.empty else None
    train_days7 = int(recent7["is_training_day"].sum())

    bf = body["body_fat_percentage"].dropna()
    latest_bf = bf.iloc[-1] if not bf.empty else None

    w_unit = "lb" if imperial else "kg"
    w_factor = KG_TO_LB if imperial else 1.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "体重",
        f"{latest_weight * w_factor:.1f} {w_unit}" if latest_weight is not None else "—",
        delta=f"{weight_d7 * w_factor:+.2f} {w_unit} / 7天" if weight_d7 is not None else None,
        delta_color="inverse",
    )
    c2.metric(
        "近 7 天平均热量差",
        f"{avg_balance:+.0f} kcal" if avg_balance is not None else "—",
        delta="纠偏后" if corrected else None,
        delta_color="off",
    )
    c3.metric(
        "近 7 天平均蛋白质",
        f"{avg_protein:.0f} g" if avg_protein is not None else "—",
    )
    c4.metric(
        "近 7 天训练日",
        f"{train_days7} 天",
        delta=f"体脂 {latest_bf:.1f}%" if latest_bf is not None else None,
        delta_color="off",
    )

    days = st.session_state.get("range_days", 90)

    if not daily.empty:
        st.subheader("训练日历")
        st.caption("点击任意一天查看当天详情。")
        result = st_echarts(
            ec.training_calendar_option(data.filter_by_range(daily, "log_date", days)),
            events={"click": "function (params) { return [params.value[0], Date.now()]; }"},
            height="280px",
            key="calendar",
        )
        # A remount replays the last payload; the timestamp makes real clicks distinct.
        clicked = (result or {}).get("chart_event")
        if clicked and clicked != st.session_state.get("_calendar_last"):
            st.session_state["_calendar_last"] = clicked
            st.session_state["detail_date"] = clicked[0]
            st.switch_page(DETAIL_PAGE)

    st.subheader("体重趋势")
    st_echarts(
        ec.weight_trend_option(
            data.filter_by_range(body, "measured_at", days), imperial
        ),
        height="360px",
        key="overview_weight",
    )

    st.subheader("每日热量差")
    balance_mode = _mode_toggle("balance_mode")
    active_bias, intake_bias, bmr = (
        _bias_factors() if balance_mode == "纠偏后" else (0.0, 0.0, energy.DEFAULT_BMR)
    )
    if balance_mode == "纠偏后":
        st.caption(
            f"已按活动消耗 {active_bias:+.0%}、摄入 {intake_bias:+.0%} 纠偏"
            f"（基础代谢 {bmr:.0f} kcal 不动），系数在「营养」页调整。"
        )
    st_echarts(
        ec.calorie_balance_option(
            data.filter_by_range(daily, "log_date", days), active_bias, intake_bias, bmr
        ),
        height="340px",
        key="overview_balance",
    )

    if not sessions.empty:
        last = sessions.iloc[-1]
        st.caption(
            f"最近训练：{last['log_date']:%Y-%m-%d} · {last['name']}"
            + (
                f" · {int(last['duration_minutes'])} 分钟"
                if pd.notna(last["duration_minutes"])
                else ""
            )
        )


def page_day_detail() -> None:
    st.title("每日详情")
    imperial = _unit_toggle("detail")

    daily = data.load_daily_logs()
    if daily.empty:
        st.info("还没有每日记录。")
        return

    dates = daily["log_date"].dt.strftime("%Y-%m-%d").tolist()
    stored = st.session_state.get("detail_date")
    index = dates.index(stored) if stored in dates else len(dates) - 1

    prev_col, pick_col, next_col = st.columns([1, 4, 1])
    if prev_col.button("← 前一天", use_container_width=True, disabled=index == 0):
        index -= 1
    if next_col.button(
        "后一天 →", use_container_width=True, disabled=index >= len(dates) - 1
    ):
        index += 1
    picked = pick_col.selectbox(
        "日期", dates, index=index, key=f"detail_pick_{index}", label_visibility="collapsed"
    )
    st.session_state["detail_date"] = picked

    day = pd.Timestamp(picked)
    log = daily[daily["log_date"] == day].iloc[0]

    w_unit = "lb" if imperial else "kg"
    w_factor = KG_TO_LB if imperial else 1.0
    len_unit = "in" if imperial else "cm"
    len_factor = CM_TO_IN if imperial else 1.0

    body = data.load_body_measurements()
    body_day = body[body["measured_at"] == day]
    b = body_day.iloc[0] if not body_day.empty else None

    category = classify_training(
        log["training_type"], log["is_training_day"], log["active_energy"]
    )
    balance = log["calories_intake"] - log["tdee"] if log["tdee"] else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "体重",
        f"{b['weight_kg'] * w_factor:.1f} {w_unit}"
        if b is not None and pd.notna(b["weight_kg"])
        else "—",
    )
    c2.metric("摄入", f"{log['calories_intake']:.0f} kcal")
    c3.metric("TDEE", f"{log['tdee']:.0f} kcal" if log["tdee"] else "—")
    c4.metric(
        "热量差",
        f"{balance:+.0f} kcal" if balance is not None else "—",
        delta=category,
        delta_color="off",
    )

    if isinstance(log["notes"], str) and log["notes"].strip():
        st.info(log["notes"])

    st.subheader("训练详情")
    sessions = data.load_workout_sessions()
    day_sessions = sessions[sessions["log_date"] == day]
    sets = data.load_exercise_sets()
    day_sets = sets[sets["log_date"] == day]

    if day_sessions.empty and day_sets.empty:
        st.caption("这天没有训练记录。")
    else:
        for _, session in day_sessions.iterrows():
            bits = [session["name"]]
            if pd.notna(session["duration_minutes"]):
                bits.append(f"{int(session['duration_minutes'])} 分钟")
            if pd.notna(session["active_energy_kcal"]):
                bits.append(f"{session['active_energy_kcal']:.0f} kcal")
            st.markdown("**" + " · ".join(bits) + "**")

            session_sets = day_sets[day_sets["session_id"] == session["id"]].copy()
            if session_sets.empty:
                continue
            if imperial:
                session_sets["weight_kg"] = (
                    session_sets["weight_kg"] * KG_TO_LB
                ).round(1)
            st.dataframe(
                summarize_sets(session_sets.sort_values("set_number"), w_unit),
                use_container_width=True,
                hide_index=True,
            )

            volume = (session_sets["weight_kg"] * session_sets["reps"]).sum()
            st.caption(
                f"{len(session_sets)} 组 · 总容量 {volume:,.0f} {w_unit}"
            )

    st.subheader("饮食详情")
    entries = data.load_nutrition_entries()
    day_entries = entries[entries["log_date"] == day].copy()

    if day_entries.empty:
        st.caption("这天没有饮食记录。")
    else:
        if imperial:
            grams = day_entries["unit"] == "g"
            day_entries.loc[grams, "amount"] = (
                day_entries.loc[grams, "amount"] * G_TO_OZ
            ).round(2)
            day_entries.loc[grams, "unit"] = "oz"

        order = {m: i for i, m in enumerate(MEAL_ORDER)}
        meals = sorted(
            day_entries["meal_type"].unique(), key=lambda m: order.get(m, 99)
        )
        for meal in meals:
            rows = day_entries[day_entries["meal_type"] == meal]
            st.markdown(
                f"**{MEAL_LABELS.get(meal, meal)}** · {rows['calories'].sum():.0f} kcal"
            )
            table = rows[
                ["food_name", "brand", "amount", "unit", "calories", "protein_g", "net_carbs_g", "fat_g"]
            ].round(
                # Snapshots carry per-gram arithmetic through to 4 decimals.
                {"amount": 1, "calories": 0, "protein_g": 1, "net_carbs_g": 1, "fat_g": 1}
            ).rename(
                columns={
                    "food_name": "食物",
                    "brand": "品牌",
                    "amount": "数量",
                    "unit": "单位",
                    "calories": "热量",
                    "protein_g": "蛋白质 g",
                    "net_carbs_g": "净碳水 g",
                    "fat_g": "脂肪 g",
                }
            )
            st.dataframe(table, use_container_width=True, hide_index=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("蛋白质", f"{log['protein_g']:.0f} g")
        m2.metric("净碳水", f"{log['net_carbs_g']:.0f} g")
        m3.metric("脂肪", f"{log['fat_g']:.0f} g")

    st.subheader("身体指标")
    if b is None:
        st.caption("这天没有身体测量记录。")
    else:
        b1, b2, b3, b4 = st.columns(4)
        b1.metric(
            "体重",
            f"{b['weight_kg'] * w_factor:.2f} {w_unit}"
            if pd.notna(b["weight_kg"])
            else "—",
        )
        b2.metric(
            "腰围",
            f"{b['waist_cm'] * len_factor:.1f} {len_unit}"
            if pd.notna(b["waist_cm"])
            else "—",
        )
        b3.metric(
            "体脂",
            f"{b['body_fat_percentage']:.1f} %"
            if pd.notna(b["body_fat_percentage"])
            else "—",
        )
        b4.metric(
            "静息心率",
            f"{int(b['resting_heart_rate'])} bpm"
            if pd.notna(b["resting_heart_rate"])
            else "—",
        )


GIRTH_COLUMNS = [
    "neck_cm", "shoulder_cm", "chest_cm", "waist_cm", "hip_cm",
    "arm_left_cm", "arm_right_cm", "forearm_left_cm", "forearm_right_cm",
    "leg_left_cm", "leg_right_cm", "calf_left_cm", "calf_right_cm",
]


def _body_figure_section(body: pd.DataFrame, imperial: bool) -> None:
    """Girths marked on a body diagram, one measuring session at a time."""
    st.subheader("身体维度")

    # Waist is logged almost daily; a session means a round of several sites.
    sessions = body[body[GIRTH_COLUMNS].notna().sum(axis=1) >= 2]
    if sessions.empty:
        st.caption("还没有围度记录。")
        return

    dates = sessions["measured_at"].dt.strftime("%Y-%m-%d").tolist()
    picked = st.selectbox(
        "测量日期", dates[::-1], key="figure_date", label_visibility="collapsed"
    )
    index = dates.index(picked)
    row = sessions.iloc[index]
    prev = sessions.iloc[index - 1] if index > 0 else None

    # st.html strips SVG; st.image renders an SVG string as-is.
    st.image(body_figure.body_figure_svg(row, prev, imperial), width=640)

    missing = [c for c in GIRTH_COLUMNS if pd.isna(row.get(c))]
    caption = f"共 {len(dates)} 次围度测量。"
    if prev is not None:
        caption += f"小字为相对上次（{dates[index - 1]}）的变化。"
    if missing:
        caption += f"虚线部位这次没量：{len(missing)} 项。"
    st.caption(caption)


def page_body() -> None:
    st.title("身体指标")
    imperial = _unit_toggle("body")

    body = data.load_body_measurements()
    if body.empty:
        st.info("还没有身体测量数据。")
        return

    _body_figure_section(body, imperial)

    days = st.session_state.get("range_days", 90)
    windowed = data.filter_by_range(body, "measured_at", days)

    st.subheader("体重")
    st_echarts(
        ec.weight_trend_option(windowed, imperial), height="360px", key="body_weight"
    )

    if windowed["waist_cm"].notna().any():
        st.subheader("腰围")
        st_echarts(
            ec.waist_trend_option(windowed, imperial), height="320px", key="body_waist"
        )

    with st.expander("测量记录表"):
        table = body.sort_values("measured_at", ascending=False).copy()
        table["measured_at"] = table["measured_at"].dt.strftime("%Y-%m-%d")
        if imperial:
            table["weight_kg"] = (table["weight_kg"] * KG_TO_LB).round(2)
            table["waist_cm"] = (table["waist_cm"] * CM_TO_IN).round(2)
        st.dataframe(
            table.rename(
                columns={
                    "measured_at": "日期",
                    "weight_kg": "体重 lb" if imperial else "体重 kg",
                    "body_fat_percentage": "体脂 %",
                    "waist_cm": "腰围 in" if imperial else "腰围 cm",
                    "resting_heart_rate": "静息心率",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def _mode_toggle(key: str) -> str:
    """Raw / corrected switch. Its choice is seeded and stored like the biases."""
    return st.segmented_control(
        "数据口径",
        ["原始", "纠偏后"],
        key=key,
        label_visibility="collapsed",
    )


def _bias_factors() -> tuple[float, float, float]:
    """Current correction factors, as set by the controls further down the page.

    Widget state is committed before the rerun, so charts above the controls
    still read the value the user just picked.
    """
    return (
        st.session_state.get("bias_active", settings.DEFAULTS["bias_active"]) / 100,
        st.session_state.get("bias_intake", settings.DEFAULTS["bias_intake"]) / 100,
        float(st.session_state.get("bias_bmr", settings.DEFAULTS["bias_bmr"])),
    )


def _corrected_balance_section(windowed: pd.DataFrame, imperial: bool) -> None:
    """Bias-corrected calorie balance with user-set correction factors."""
    st.subheader("热量差纠偏")
    st.caption(
        "基础代谢基本只随体重变化、日间波动小，所以只对活动消耗纠偏："
        "TDEE 减去下面的基础代谢基线得到活动消耗，再按系数缩放；摄入按手记低估的方向单独调整。"
        "这组系数同时用于上方「摄入 vs TDEE」的纠偏视图。"
    )

    left, mid, right = st.columns([2, 2, 1])
    active_bias = left.slider(
        "活动消耗偏差", -80, 20, step=1, format="%d%%", key="bias_active",
        help="负值表示实际活动消耗低于记录值（手环高估了活动）。基础代谢不受影响。",
    ) / 100
    intake_bias = mid.slider(
        "摄入偏差", -10, 30, step=1, format="%d%%", key="bias_intake",
        help="正值表示实际摄入高于记录值（记录低估了摄入）。",
    ) / 100
    bmr = float(
        right.number_input(
            "基础代谢", min_value=1000, max_value=3000, step=10, key="bias_bmr",
            help="记录 TDEE 所基于的静息代谢，用于把活动消耗拆出来。",
        )
    )

    base, active = energy.split_tdee(windowed, bmr)
    st.caption(
        f"这段区间活动消耗日均 {active.mean():.0f} kcal"
        f"（占 TDEE 的 {active.mean() / (base.mean() + active.mean()):.0%}），"
        f"纠偏后为 {active.mean() * (1 + active_bias):.0f} kcal。"
    )

    st_echarts(
        ec.corrected_balance_option(windowed, active_bias, intake_bias, bmr),
        height="360px",
        key="nut_corrected",
    )

    cal = energy.calibration(
        windowed, data.load_body_measurements(), active_bias, intake_bias, bmr
    )
    if cal is None:
        st.caption("这段区间的数据不足以和体重变化对照。")
        return

    w_unit = "lb" if imperial else "kg"
    w_factor = KG_TO_LB if imperial else 1.0

    c1, c2, c3 = st.columns(3)
    c1.metric("纠偏后日均热量差", f"{cal['mean_balance']:+.0f} kcal")
    c2.metric(
        f"预测体重变化 · {cal['days']} 天",
        f"{cal['predicted_kg'] * w_factor:+.2f} {w_unit}",
    )
    c3.metric(
        "实测体重变化",
        f"{cal['actual_kg'] * w_factor:+.2f} {w_unit}",
        delta=f"差 {cal['residual_per_day']:+.0f} kcal/天",
        delta_color="off",
    )
    st.caption(
        f"预测按 {energy.KCAL_PER_KG:.0f} kcal/kg 换算，体重取 7 日平滑值首末之差。"
        "两侧偏差只有一个方程、两个未知数，所以「差」是两边合计的净误差，"
        "调到接近 0 说明这组系数与实测吻合——但体重还受水分和糖原影响，别追求精确归零。"
    )


def page_nutrition() -> None:
    st.title("营养")
    imperial = _unit_toggle("nutrition")
    if imperial:
        st.caption("宏量营养素按行业惯例始终以克显示；英制仅影响饮食明细中以克计的食物数量（盎司）。")

    daily = data.load_daily_logs()
    if daily.empty:
        st.info("还没有每日记录。")
        return

    days = st.session_state.get("range_days", 90)
    windowed = data.filter_by_range(daily, "log_date", days)

    st.subheader("摄入 vs TDEE")
    mode = _mode_toggle("intake_mode")
    active_bias, intake_bias, bmr = (
        _bias_factors() if mode == "纠偏后" else (0.0, 0.0, energy.DEFAULT_BMR)
    )
    if mode == "纠偏后":
        st.caption(
            f"已按活动消耗 {active_bias:+.0%}、摄入 {intake_bias:+.0%} 缩放"
            f"（基础代谢 {bmr:.0f} kcal 不动），系数在下方「热量差纠偏」中调整。"
        )
    st_echarts(
        ec.intake_vs_tdee_option(windowed, active_bias, intake_bias, bmr),
        height="360px",
        key="nut_intake",
    )

    _corrected_balance_section(windowed, imperial)

    st.subheader("三大营养素")
    st_echarts(ec.macro_stack_option(windowed), height="360px", key="nut_macros")

    st.subheader("蛋白质")
    st_echarts(ec.protein_trend_option(windowed), height="320px", key="nut_protein")

    entries = data.load_nutrition_entries()
    if not entries.empty:
        st.caption("按日查看完整饮食明细请前往「每日详情」页。")


PINNED_SLOTS = 6


def _move_pinned(index: int, step: int) -> None:
    """Swap a panel with its neighbour and redraw in the new order."""
    order = list(st.session_state.get("pinned_exercises", []))
    target = index + step
    if 0 <= target < len(order):
        order[index], order[target] = order[target], order[index]
        st.session_state["pinned_exercises"] = order
        st.rerun()


def _pinned_progression(sets: pd.DataFrame, imperial: bool) -> None:
    """The exercises kept in view, each with its top set and session volume."""
    st.subheader("动作进步曲线")

    counts = sets.groupby("exercise").size().sort_values(ascending=False)
    options = counts.index.tolist()

    # A merged or renamed exercise can leave a stored name with no data behind
    # it; the picker would refuse a value that is not among its options.
    stored = [e for e in st.session_state.get("pinned_exercises", []) if e in options]

    with st.expander("常驻动作与排版", expanded=not stored):
        picked = st.multiselect(
            "常驻动作",
            options,
            default=stored,
            max_selections=PINNED_SLOTS,
            key="pinned_pick",
            help="最多 6 个。",
        )
        st.segmented_control(
            "每行显示",
            [1, 2, 3],
            key="pinned_columns",
            format_func=lambda n: f"每行 {n} 个",
        )

    # The picker decides membership; the stored list decides order, so adding
    # an exercise appends it instead of reshuffling what is already arranged.
    pinned = [e for e in stored if e in picked] + [e for e in picked if e not in stored]
    if pinned != st.session_state.get("pinned_exercises"):
        st.session_state["pinned_exercises"] = pinned
    if not pinned:
        st.caption("还没有选择常驻动作。")
        return

    columns_per_row = st.session_state.get("pinned_columns") or 2
    height = {1: "320px", 2: "230px", 3: "210px"}[columns_per_row]

    for row_start in range(0, len(pinned), columns_per_row):
        row = pinned[row_start : row_start + columns_per_row]
        for column, exercise in zip(st.columns(columns_per_row), row):
            with column:
                index = pinned.index(exercise)
                left, right, _ = st.columns([1, 1, 6])
                if left.button(
                    "←", key=f"tr_up_{exercise}", disabled=index == 0,
                    help="前移", use_container_width=True,
                ):
                    _move_pinned(index, -1)
                if right.button(
                    "→", key=f"tr_down_{exercise}", disabled=index == len(pinned) - 1,
                    help="后移", use_container_width=True,
                ):
                    _move_pinned(index, 1)
                st_echarts(
                    ec.exercise_panel_option(sets, exercise, imperial),
                    height=height,
                    key=f"tr_pin_{exercise}",
                )

    # Anything not pinned is still one dropdown away.
    others = [e for e in options if e not in pinned]
    if not others:
        return
    st.markdown("**查看其他动作**")
    picked = st.selectbox(
        "其他动作", others, key="tr_other_exercise", label_visibility="collapsed"
    )
    st_echarts(
        ec.exercise_panel_option(sets, picked, imperial),
        height="300px",
        key="tr_other_panel",
    )


def page_training() -> None:
    st.title("训练")
    # Plates are marked in pounds, so the lifting page opens in imperial.
    imperial = _unit_toggle("training", default="英制")

    sets = data.load_exercise_sets()
    if sets.empty:
        st.info("还没有训练数据。")
        return

    days = st.session_state.get("range_days", 90)
    windowed = data.filter_by_range(sets, "log_date", days)

    _pinned_progression(sets, imperial)

    st.subheader("每周训练容量")
    st_echarts(
        ec.weekly_tonnage_option(windowed, imperial), height="340px", key="tr_tonnage"
    )

    st.subheader("各肌群组数")
    missing = int(windowed["muscle_group"].isna().sum())
    if missing:
        st.caption(
            f"{missing} / {len(windowed)} 组的动作没有登记肌群，未计入下图。"
            "补齐 `exercises.muscle_group` 后即可显示。"
        )
    height = max(300, 26 * windowed["muscle_group"].nunique())
    st_echarts(
        ec.muscle_group_sets_option(windowed), height=f"{height}px", key="tr_muscles"
    )


OVERVIEW_PAGE = st.Page(page_overview, title="概览", icon="📊", default=True)
DETAIL_PAGE = st.Page(page_day_detail, title="每日详情", icon="📅", url_path="day")
BODY_PAGE = st.Page(page_body, title="身体指标", icon="⚖️", url_path="body")
NUTRITION_PAGE = st.Page(page_nutrition, title="营养", icon="🥗", url_path="nutrition")
TRAINING_PAGE = st.Page(page_training, title="训练", icon="🏋️", url_path="training")


def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    _init_settings()
    st.session_state["range_days"] = _sidebar_range()

    nav = st.navigation(
        [OVERVIEW_PAGE, DETAIL_PAGE, BODY_PAGE, NUTRITION_PAGE, TRAINING_PAGE]
    )
    nav.run()
    _persist_settings()


main()
