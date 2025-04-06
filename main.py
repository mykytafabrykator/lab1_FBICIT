from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, abort, redirect, render_template, request, url_for
from markupsafe import Markup


Item = Dict[str, Any]

app: Flask = Flask(__name__)
DATA_FILE: Path = Path("data.json")


def load_items() -> List[Item]:
    """Читає JSON‑файл і повертає список елементів."""
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open(encoding="utf-8") as fp:
        return json.load(fp)


def save_items() -> None:
    """Записує поточний ITEMS до JSON‑файлу."""
    with DATA_FILE.open("w", encoding="utf-8") as fp:
        json.dump(ITEMS, fp, ensure_ascii=False, indent=2)


ITEMS: List[Item] = load_items()
current_id: int = max((i["N"] for i in ITEMS), default=0)


def get_children(parent_id: int) -> List[Item]:
    return [item for item in ITEMS if item["Parent"] == parent_id]


def find_item(node_id: int) -> Optional[Item]:
    return next((item for item in ITEMS if item["N"] == node_id), None)


def clone_subtree(src_id: int, new_parent: int) -> Optional[int]:
    """
    Рекурсивно копіює вузол `src_id` і всіх його нащадків.
    Повертає ID кореня нової копії.
    """
    global current_id

    src_item = find_item(src_id)
    if src_item is None:
        return None

    current_id += 1
    new_id = current_id
    ITEMS.append(
        {
            "N": new_id,
            "Parent": new_parent,
            "Name": f'{src_item["Name"]} (copy)',
        }
    )

    for child in get_children(src_id):
        clone_subtree(child["N"], new_id)

    return new_id


def get_subtree_ids(node_id: int) -> List[int]:
    """Повертає всі ID у піддереві вузла (включно з ним самим)."""
    ids: List[int] = [node_id]
    for child in get_children(node_id):
        ids.extend(get_subtree_ids(child["N"]))
    return ids


def delete_subtree(node_id: int) -> None:
    """Видаляє вузол і всіх його нащадків."""
    global ITEMS
    subtree: set[int] = set(get_subtree_ids(node_id))
    ITEMS = [item for item in ITEMS if item["N"] not in subtree]


def reassign_children_to_parent(node_id: int) -> None:
    """Видаляє вузол, а його дітей «піднімає» до батька вузла."""
    item = find_item(node_id)
    if item is None:
        return

    for child in get_children(node_id):
        child["Parent"] = item["Parent"]

    ITEMS.remove(item)


def render_tree_html(
    parent_id: int, highlight: Optional[int] = None
) -> Markup:
    """Рекурсивно формує HTML‑розмітку дерева."""
    children = get_children(parent_id)
    if not children:
        return Markup("")

    parts: List[str] = ["<ul>"]
    for child in children:
        has_kids = bool(get_children(child["N"]))
        toggle_btn = (
            f'<span id="toggle-btn-{child["N"]}" class="toggle-btn" '
            f'onclick="toggleNode({child["N"]})">[-]</span>'
            if has_kids
            else ""
        )

        selected_cls = " selected" if highlight == child["N"] else ""
        link = (
            f'<span class="tree-link{selected_cls}" '
            f'onclick="gotoNode({child["N"]})">{child["Name"]}</span>'
        )

        open_div = f'<div id="children-{child["N"]}">' if has_kids else ""
        close_div = "</div>" if has_kids else ""

        parts.append(
            f'<li class="tree-node">{toggle_btn}{link}'
            f'{open_div}{render_tree_html(child["N"], highlight)}'
            f'{close_div}</li>'
        )
    parts.append("</ul>")
    return Markup("".join(parts))


@app.route("/")
def index():
    highlight: Optional[int] = request.args.get("sel", type=int)
    return render_template(
        "index.html",
        items=ITEMS,
        render_tree=lambda pid: render_tree_html(pid, highlight),
        highlight=highlight,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        parent: int = request.args.get("parent", 0, int)
        return render_template("add.html", parent=parent)

    global current_id
    current_id += 1
    ITEMS.append(
        {
            "N": current_id,
            "Parent": request.form.get("parent", 0, int),
            "Name": request.form["name"],
        }
    )
    save_items()
    return redirect(url_for("index", sel=current_id))


@app.route("/rename", methods=["POST"])
def rename():
    item = find_item(request.form.get("n", type=int))
    if item is not None:
        item["Name"] = request.form["new_name"].strip()
        save_items()
    return redirect(url_for("index", sel=item["N"] if item else None))


@app.route("/delete_subtree", methods=["POST"])
def delete_subtree_route():
    delete_subtree(request.form.get("n", type=int))
    save_items()
    return redirect(url_for("index"))


@app.route("/delete_reassign", methods=["POST"])
def delete_reassign_route():
    reassign_children_to_parent(request.form.get("n", type=int))
    save_items()
    return redirect(url_for("index"))


@app.route("/duplicate", methods=["POST"])
def duplicate():
    src_id: int = request.form.get("n", type=int)
    parent_id: int = find_item(src_id)["Parent"]  # type: ignore[index]
    new_id: Optional[int] = clone_subtree(src_id, parent_id)
    save_items()
    return redirect(url_for("index", sel=new_id))


@app.route("/move", methods=["POST"])
def move():
    node_id: int = request.form.get("n", type=int)
    new_parent: int = request.form.get("new_parent", type=int)

    item = find_item(node_id)
    target_parent = find_item(new_parent) if new_parent else None
    if item is None or (new_parent and target_parent is None):
        abort(400)

    if new_parent in get_subtree_ids(node_id):
        abort(400, "Cannot move into own subtree")

    item["Parent"] = new_parent
    save_items()
    return redirect(url_for("index", sel=node_id))


if __name__ == "__main__":
    app.run(debug=True)
