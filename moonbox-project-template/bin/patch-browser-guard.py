#!/usr/bin/env python3
import pathlib
import sys


BROWSER_GUARD = pathlib.Path("/app/browser_guard.py")


def main() -> int:
    if not BROWSER_GUARD.exists():
        print(f"{BROWSER_GUARD} does not exist", file=sys.stderr)
        return 1

    text = BROWSER_GUARD.read_text(encoding="utf-8")

    focus_block = """            x, y = pyautogui.position()
            width, _ = get_screensize()
            pyautogui.click(width - 25, 115)
            pyautogui.moveTo(x, y)

"""
    safe_focus_block = """            try:
                x, y = pyautogui.position()
                width, _ = get_screensize()
                pyautogui.click(width - 25, 115)
                pyautogui.moveTo(x, y)
            except Exception as exc:
                logger.warning(f"Skipping browser focus click: {exc}")

"""
    focus_count = text.count(focus_block)
    if focus_count == 0:
        print("browser focus block was not found in browser_guard.py", file=sys.stderr)
        return 1
    text = text.replace(focus_block, safe_focus_block)

    BROWSER_GUARD.write_text(text, encoding="utf-8")
    print(f"patched {BROWSER_GUARD}: focus blocks={focus_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
