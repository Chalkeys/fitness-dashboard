"""A drag-to-reorder chip strip, as a Streamlit inline component.

Streamlit has no widget for ordering things, and its own multiselect chips
cannot be dragged. This is the smallest thing that can: a row of chips that
reports a new order once the drag ends.

Dragging is done with pointer events rather than HTML5 drag-and-drop so that a
touch screen works the same as a mouse. The drop target is found by hit-testing
the chips' own rectangles, which avoids `elementFromPoint` having to reach
through the component's shadow root.
"""

from __future__ import annotations

import streamlit as st

from dashboard.theme import BASELINE, BLUE, INK_SECONDARY, MUTED, SURFACE

_CSS = f"""
.sortable {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 2px 0 6px;
}}
.chip {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 10px;
    border: 1px solid {BASELINE};
    border-radius: 999px;
    background: {SURFACE};
    color: {INK_SECONDARY};
    font-size: 13px;
    font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    cursor: grab;
    user-select: none;
    touch-action: none;
}}
.chip .grip {{ color: {MUTED}; font-size: 11px; letter-spacing: -1px; }}
.chip.dragging {{ opacity: 0.45; cursor: grabbing; }}
.chip.over {{ border-color: {BLUE}; box-shadow: inset 0 0 0 1px {BLUE}; }}
"""

_JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  // The entry point runs again on every rerun; appending unconditionally would
  // leave a second strip behind each time.
  let root = parentElement.querySelector(".sortable");
  if (!root) {
    root = document.createElement("div");
    root.className = "sortable";
    parentElement.appendChild(root);
  }

  let order = Array.isArray(data) ? [...data] : [];
  let dragIndex = null;
  let targetIndex = null;

  const chips = () => Array.from(root.querySelectorAll(".chip"));

  // Hit-test the chips themselves: the component sits in a shadow root, where
  // document.elementFromPoint would only ever return the host.
  function chipAt(x, y) {
    return chips().findIndex((c) => {
      const r = c.getBoundingClientRect();
      return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    });
  }

  function clearMarks() {
    chips().forEach((c) => c.classList.remove("over", "dragging"));
  }

  function render() {
    root.innerHTML = "";
    order.forEach((name, index) => {
      const chip = document.createElement("div");
      chip.className = "chip";
      chip.innerHTML = '<span class="grip">⠿</span>';
      chip.appendChild(document.createTextNode(name));
      chip.dataset.index = String(index);

      chip.addEventListener("pointerdown", (event) => {
        dragIndex = index;
        targetIndex = null;
        chip.setPointerCapture(event.pointerId);
        chip.classList.add("dragging");
      });

      chip.addEventListener("pointermove", (event) => {
        if (dragIndex === null) return;
        const found = chipAt(event.clientX, event.clientY);
        targetIndex = found >= 0 && found !== dragIndex ? found : null;
        chips().forEach((c, i) => c.classList.toggle("over", i === targetIndex));
      });

      const finish = () => {
        if (dragIndex !== null && targetIndex !== null) {
          const next = [...order];
          next.splice(targetIndex, 0, next.splice(dragIndex, 1)[0]);
          order = next;
          render();
          setTriggerValue("order", order);
        } else {
          clearMarks();
        }
        dragIndex = null;
        targetIndex = null;
      };
      chip.addEventListener("pointerup", finish);
      chip.addEventListener("pointercancel", finish);

      root.appendChild(chip);
    });
  }

  render();
}
"""

_component = st.components.v2.component("fitness.sortable", css=_CSS, js=_JS)


def sortable_order(items: list[str], key: str) -> list[str] | None:
    """Render `items` as draggable chips; return a new order once dragged."""
    if not items:
        return None
    result = _component(
        key=key,
        data=items,
        on_order_change=lambda: None,
    )
    order = getattr(result, "order", None)
    # Only a complete permutation is worth acting on; anything else means the
    # component is echoing a stale drag from before the list changed.
    if isinstance(order, list) and sorted(order) == sorted(items):
        return order
    return None
