"""Runner minimo sin pytest: ejecuta toda funcion test_* de los modulos indicados."""
import importlib
import sys
import traceback

MODULES = ["tests.test_gestures", "tests.test_actions", "tests.test_hud", "tests.test_recorder",
           "tests.test_assistant"]

def main():
    total = passed = 0
    failures = []
    for modname in MODULES:
        mod = importlib.import_module(modname)
        names = [n for n in dir(mod) if n.startswith("test_")]
        for name in names:
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            total += 1
            try:
                fn()
                passed += 1
            except Exception:
                failures.append((modname, name, traceback.format_exc()))
    print(f"{passed}/{total} passed")
    for modname, name, tb in failures:
        print(f"\nFAIL {modname}.{name}\n{tb}")
    return 0 if not failures else 1

if __name__ == "__main__":
    sys.exit(main())
