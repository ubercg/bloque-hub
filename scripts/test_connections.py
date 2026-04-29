import os
from litellm import completion
from config.settings import IMPLEMENTER_MODEL, EXPLORER_MODEL


def test_models():
    print("--- Verificando Conexiones de BLOQUE HUB ---")

    # 1. Probar Anthropic
    print(f"Testing Anthropic with model: {IMPLEMENTER_MODEL}")
    try:
        resp = completion(
            model=IMPLEMENTER_MODEL,
            messages=[{"role": "user", "content": "hi"}],
        )
        print("✅ Anthropic OK")
    except Exception as e:
        print(f"❌ Anthropic Error: {e}")

    # 2. Probar Google / Gemini
    print(f"\nTesting Gemini with model: {EXPLORER_MODEL}")
    try:
        resp = completion(
            model=EXPLORER_MODEL,
            messages=[{"role": "user", "content": "hi"}],
        )
        print("✅ Gemini OK")
    except Exception as e:
        print(f"❌ Gemini Error: {e}")


if __name__ == "__main__":
    test_models()
