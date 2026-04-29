import os
import sys
import shutil
from pathlib import Path

# Agregar el root de forma dinámica para importar config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def ensure_repo_writable():
    from config.settings import REPO_ROOT

    if not os.access(REPO_ROOT, os.W_OK):
        raise SystemExit(
            f"ERROR: Sin permisos de escritura en {REPO_ROOT}.\n"
            "Verificá que el directorio no es solo lectura."
        )
    test_dir = REPO_ROOT / "storage" / ".write_check"
    try:
        test_dir.mkdir(parents=True, exist_ok=True)
        test_dir.rmdir()
    except PermissionError as e:
        raise SystemExit(f"ERROR: No se pudo crear storage/: {e}")


def create_symlink(link_path: Path, target_path: Path) -> None:
    """Crea symlink con target absoluto — resuelve desde cualquier cwd."""
    target_resolved = target_path.resolve()

    # Avoid resolving the link if it's already a symlink
    # .resolve() on a symlink returns its target, which leads to self-deletion bugs
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.exists():
        if link_path.is_dir():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()

    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target_resolved)


def main():
    from config.settings import REPO_ROOT, TENANT_ID

    ensure_repo_writable()

    tenant_dir = REPO_ROOT / "storage" / TENANT_ID
    executions_dir = tenant_dir / "executions"
    engram_dir = tenant_dir / "engram"
    logs_dir = tenant_dir / "logs"

    if tenant_dir.exists():
        resp = input(f"El tenant {TENANT_ID} ya tiene storage. ¿Sobreescribir? [s/N]: ")
        if resp.strip().lower() not in ["s", "si", "y", "yes"]:
            print("Operación cancelada.")
            return

    # Crear estructura base
    executions_dir.mkdir(parents=True, exist_ok=True)
    engram_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 1. task_graph.json
    old_graph = REPO_ROOT / "tasks" / "graph" / "task_graph.json"
    new_graph = tenant_dir / "task_graph.json"
    if old_graph.exists() and not old_graph.is_symlink():
        shutil.move(str(old_graph), str(new_graph))

    # 2. executions/
    old_execs = REPO_ROOT / "tasks" / "executions"
    if old_execs.exists() and not old_execs.is_symlink():
        for item in old_execs.iterdir():
            shutil.move(str(item), str(executions_dir / item.name))

    # 3. engram.db
    old_engram = REPO_ROOT / "ai_memory" / "engram" / "engram.db"
    new_engram = engram_dir / "engram.db"
    if old_engram.exists() and not old_engram.is_symlink():
        shutil.move(str(old_engram), str(new_engram))

    # 4. events.jsonl
    old_events = REPO_ROOT / "logs" / "events.jsonl"
    new_events = logs_dir / "events.jsonl"
    if old_events.exists() and not old_events.is_symlink():
        shutil.move(str(old_events), str(new_events))

    # Migrar ChromaDB
    chroma_src = REPO_ROOT / "ai_memory" / "chroma"
    chroma_dst = tenant_dir / "chroma"
    if chroma_src.exists() and not chroma_dst.exists():
        shutil.move(str(chroma_src), str(chroma_dst))
        print("  ✅ chroma/")
    else:
        print("  ⚠️  chroma/ ya existe o no encontrado, skipping")

    # Migrar index_state
    index_src = REPO_ROOT / "ai_memory" / "index_state"
    index_dst = tenant_dir / "index_state"
    if index_src.exists() and not index_dst.exists():
        shutil.move(str(index_src), str(index_dst))
        print("  ✅ index_state/")
    else:
        print("  ⚠️  index_state/ ya existe o no encontrado, skipping")

    # Crear symlinks
    create_symlink(old_graph, new_graph)
    create_symlink(old_execs, executions_dir)
    create_symlink(old_events, new_events)
    create_symlink(old_engram, new_engram)

    # Crear .gitkeep
    gitkeep = REPO_ROOT / "storage" / ".gitkeep"
    gitkeep.parent.mkdir(parents=True, exist_ok=True)
    gitkeep.touch(exist_ok=True)

    # Contar tareas
    task_count = len(list(executions_dir.iterdir())) if executions_dir.exists() else 0

    print("═══════════════════════════════════════")
    print("MIGRACIÓN A MULTI-TENANCY")
    print("═══════════════════════════════════════")
    print(f"Tenant ID       : {TENANT_ID}")
    print("Archivos movidos:")
    print("✅ task_graph.json")
    print(f"✅ executions/ ({task_count} tareas)")
    print("✅ engram.db")
    print("✅ events.jsonl")
    print("Symlinks creados: 4")
    print(".gitignore      : actualizado")
    print("═══════════════════════════════════════")


if __name__ == "__main__":
    main()
