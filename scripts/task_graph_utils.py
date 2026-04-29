"""
Utility scripts para gestionar el task graph desde fish shell.
Uso:
    poetry run python scripts/task_graph_utils.py --stuck
    poetry run python scripts/task_graph_utils.py --reset
    poetry run python scripts/task_graph_utils.py --summary
    poetry run python scripts/task_graph_utils.py --complete TASK-004
    poetry run python scripts/task_graph_utils.py --fail TASK-004
    poetry run python scripts/task_graph_utils.py --pending TASK-004
    poetry run python scripts/task_graph_utils.py --status TASK-004
    poetry run python scripts/task_graph_utils.py --unblocks TASK-004
    poetry run python scripts/task_graph_utils.py --execute TASK-004
"""

import json
import argparse
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import TASK_GRAPH_PATH, TASK_EXECUTIONS

TASK_GRAPH = TASK_GRAPH_PATH
EXEC_DIR = TASK_EXECUTIONS


def load():
    return json.loads(TASK_GRAPH.read_text())


def save(g):
    TASK_GRAPH.write_text(json.dumps(g, indent=2, ensure_ascii=False))


def find_task(g, task_id):
    return next((t for t in g["tasks"] if t["id"] == task_id), None)


def show_stuck(g):
    stuck = [t for t in g["tasks"] if t.get("status") == "in_progress"]
    print(f"Stuck tasks: {len(stuck)}")
    for t in stuck:
        print(f"  {t['id']} [{t['status']}] - {t['title']}")
    return stuck


def reset_stuck(g):
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for t in g["tasks"]:
        if t.get("status") == "in_progress":
            t["status"] = "pending"
            t["updated_at"] = now
            print(f"  Reset → pending: {t['id']} - {t['title']}")
            count += 1
    save(g)
    print(f"task_graph.json guardado. ({count} tareas reseteadas)")


def show_summary(g):
    statuses = {}
    for t in g["tasks"]:
        s = t.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    print("Task Summary:")
    for s, count in sorted(statuses.items()):
        print(f"  {s}: {count}")


def set_status(g, task_id, new_status):
    task = find_task(g, task_id)
    if not task:
        print(f"ERROR: Task {task_id} not found.")
        return

    if "tenant_id" not in task:
        task["tenant_id"] = os.getenv("TENANT_ID", "bloque-hub")

    old = task.get("status")
    task["status"] = new_status
    task["updated_at"] = datetime.now(timezone.utc).isoformat()
    save(g)
    print(f"  {task_id}: {old} → {new_status}  ({task['title']})")
    print("task_graph.json guardado.")


def show_status(g, task_id):
    task = find_task(g, task_id)
    if not task:
        print(f"ERROR: Task {task_id} not found.")
        return
    print(f"  {task['id']} [{task['status']}] - {task['title']}")
    deps = task.get("depends_on", [])
    if deps:
        print(f"  depends_on: {', '.join(deps)}")
        for dep_id in deps:
            dep = find_task(g, dep_id)
            if dep:
                print(f"    {dep['id']} [{dep['status']}] - {dep['title']}")


def show_unblocked_by(g, task_id):
    unblocked = [
        t
        for t in g["tasks"]
        if task_id in t.get("depends_on", []) and t.get("status") == "pending"
    ]
    if unblocked:
        print(f"\nTareas que se desbloquean al completar {task_id}:")
        for t in unblocked:
            print(f"  {t['id']} - {t['title']}")
    else:
        print(f"\nNinguna tarea pendiente depende directamente de {task_id}.")


def execute_task(g, task_id, pipeline=True):
    task = find_task(g, task_id)
    if not task:
        print(f"ERROR: Task {task_id} not found.")
        return

    deps = task.get("depends_on", [])
    for dep_id in deps:
        dep = find_task(g, dep_id)
        if dep and dep.get("status") != "completed":
            print(
                f"ERROR: Task {task_id} depends on {dep_id} [{dep.get('status')}]. Complete {dep_id} first."
            )
            return

    print(f"Executing {task_id}: {task['title']}")
    print(f"Type: {task.get('type', 'unknown')}")

    task["status"] = "running"
    task["updated_at"] = datetime.now(timezone.utc).isoformat()
    save(g)
    print(f"Status updated to 'running'")

    cmd = ["poetry", "run", "python", "-m", "ai_system.execution.orchestrator"]
    if pipeline:
        cmd.append("--pipeline")
    cmd.extend(["--task", task_id])

    env = os.environ.copy()
    env["AI_MODEL"] = env.get("AI_MODEL", "gemini/gemini-2.5-flash")
    env["PLANNER_MODEL"] = env.get("PLANNER_MODEL", "gemini/gemini-2.5-flash")
    env["IMPLEMENTER_MODEL"] = env.get("IMPLEMENTER_MODEL", "gemini/gemini-2.5-flash")

    print(f"\nRunning: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, env=env)

    if result.returncode == 0:
        set_status(g, task_id, "completed")
    else:
        set_status(g, task_id, "failed")

    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stuck", action="store_true", help="Ver tareas en in_progress"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Resetear in_progress → pending"
    )
    parser.add_argument("--summary", action="store_true", help="Ver resumen de estados")
    parser.add_argument(
        "--list",
        type=str,
        metavar="STATUS",
        nargs="?",
        const="all",
        help="Listar tareas: --list pending | completed | failed | all",
    )
    parser.add_argument(
        "--complete", type=str, metavar="TASK_ID", help="Marcar tarea como completed"
    )
    parser.add_argument(
        "--fail", type=str, metavar="TASK_ID", help="Marcar tarea como failed"
    )
    parser.add_argument(
        "--pending", type=str, metavar="TASK_ID", help="Marcar tarea como pending"
    )
    parser.add_argument(
        "--status", type=str, metavar="TASK_ID", help="Ver estado de una tarea"
    )
    parser.add_argument(
        "--unblocks",
        type=str,
        metavar="TASK_ID",
        help="Ver qué desbloquea completar una tarea",
    )
    parser.add_argument(
        "--execute",
        type=str,
        metavar="TASK_ID",
        help="Ejecutar tarea con orchestrator pipeline",
    )
    parser.add_argument(
        "--no-pipeline",
        action="store_true",
        help="Ejecutar sin pipeline (para --execute)",
    )
    args = parser.parse_args()

    g = load()

    if args.stuck:
        show_stuck(g)
    elif args.reset:
        show_stuck(g)
        print()
        reset_stuck(g)
    elif args.summary:
        show_summary(g)
    elif args.list is not None:
        status_filter = args.list
        tasks = g["tasks"]
        if status_filter != "all":
            tasks = [t for t in tasks if t.get("status") == status_filter]
        tasks = sorted(tasks, key=lambda t: (t.get("status", ""), t["id"]))
        print(f"\n{'ID':<12} {'STATUS':<14} TITLE")
        print("-" * 70)
        for t in tasks:
            print(f"  {t['id']:<10} {t.get('status', ''):<14} {t.get('title', '')}")
        print(f"\nTotal: {len(tasks)}")
    elif args.complete:
        set_status(g, args.complete, "completed")
        show_unblocked_by(g, args.complete)
    elif args.fail:
        set_status(g, args.fail, "failed")
    elif args.pending:
        set_status(g, args.pending, "pending")
    elif args.status:
        show_status(g, args.status)
    elif args.unblocks:
        show_unblocked_by(g, args.unblocks)
    elif args.execute:
        execute_task(g, args.execute, pipeline=not args.no_pipeline)
    else:
        parser.print_help()
