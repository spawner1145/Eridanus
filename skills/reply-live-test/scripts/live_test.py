import sys
from datetime import datetime


def main() -> None:
    marker = sys.argv[1] if len(sys.argv) > 1 else "alice-live"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"SKILL_SCRIPT_RESULT: REPLY_SCRIPT_OK marker={marker} time={now}")


if __name__ == "__main__":
    main()
