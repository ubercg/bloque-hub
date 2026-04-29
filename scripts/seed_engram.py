import json
import os
from pathlib import Path
from litellm import completion
from config.settings import AI_MODEL, AI_MAX_TOKENS, AI_TEMPERATURE
from ai_memory.engram.store import EngramStore

REPO_ROOT = Path(__file__).resolve().parent.parent

MODULES_TO_SEED = [
    {"path": "src/backend/app/core/permissions.py", "scope": "core", "domain": None},
    {
        "path": "src/backend/app/modules/inventory",
        "scope": "domain",
        "domain": "proptech",
    },
    {
        "path": "src/backend/app/modules/payments",
        "scope": "domain",
        "domain": "fintech",
    },
    {"path": "src/backend/app/modules/billing", "scope": "domain", "domain": "fintech"},
]

PROMPT_TEMPLATE = """Analizá este código y extraé máximo 5 reglas de negocio o estándares arquitectónicos que SIEMPRE deben respetarse.
Formato de respuesta (JSON array):
[
  {
    "topic": "título corto de la regla",
    "learning": "descripción clara de la regla y por qué importa",
    "scope": "core | domain",
    "domain": "proptech | fintech | null",
    "confidence": 0.8,
    "context_keywords": ["keyword1", "keyword2"]
  }
]
Código a analizar:
{code}"""


def extract_code_from_path(target_path: Path) -> str:
    content = ""
    if target_path.is_file():
        content += f"--- {target_path.name} ---\n{target_path.read_text()}\n"
    elif target_path.is_dir():
        for py_file in target_path.rglob("*.py"):
            content += f"--- {py_file.name} ---\n{py_file.read_text()[:3000]}\n"  # truncating to avoid massive prompts if many files
    return content


def main():
    store = EngramStore()

    stats = {"core": 0, "proptech": 0, "fintech": 0}

    print("Starting Engram Seed Process...")

    for item in MODULES_TO_SEED:
        target_path = REPO_ROOT / item["path"]

        if not target_path.exists():
            print(f"Warning: {target_path} does not exist, skipping.")
            continue

        print(f"Analyzing {item['path']}...")
        code_content = extract_code_from_path(target_path)

        if not code_content.strip():
            print("No Python code found, skipping.")
            continue

        # Truncate content slightly if it gets too large for context
        code_content = code_content[:30000]

        prompt = PROMPT_TEMPLATE.replace("{code}", code_content)

        try:
            response = completion(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
            )

            content = response.choices[0].message.content

            # Parse response
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end].strip()

            try:
                rules = json.loads(content)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON for {item['path']}")
                continue

            for rule in rules:
                # Override scope and domain to ensure consistency with the file source
                rule_scope = item["scope"]
                rule_domain = item["domain"]

                store.add_learning(
                    task_id="SEED_SCRIPT",
                    topic=rule.get("topic", "Extracted rule"),
                    learning=rule.get("learning", ""),
                    skill_ids=["skill-architecture-base.md"],
                    context_keywords=rule.get("context_keywords", ["seed"]),
                    outcome="clean_success",
                    scope=rule_scope,
                    domain=rule_domain,
                    confidence=float(rule.get("confidence", 0.9)),
                    source="seed",
                )

                if rule_scope == "core":
                    stats["core"] += 1
                elif rule_domain == "proptech":
                    stats["proptech"] += 1
                elif rule_domain == "fintech":
                    stats["fintech"] += 1

        except Exception as e:
            print(f"Error processing {item['path']}: {e}")

    print("\n═══════════════════════════════════════")
    print("ENGRAM SEED — Resumen")
    print("═══════════════════════════════════════")
    print(f"Core learnings insertados  : {stats['core']}")
    print(f"Domain:Proptech insertados : {stats['proptech']}")
    print(f"Domain:Fintech insertados  : {stats['fintech']}")
    print(f"Total                      : {sum(stats.values())}")
    print("═══════════════════════════════════════")


if __name__ == "__main__":
    main()
