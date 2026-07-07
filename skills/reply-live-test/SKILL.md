---
name: reply-live-test
description: Use when the user asks to run a live skill test, verify dynamic skill loading, test skill scripts, or check the phrase "技能热加载测试".
---

# Reply Live Test

Use this skill only for live verification of the Eridanus reply skill loading system.

Workflow:

1. Read `references/test-data.md` with `read_skill_file`.
2. Run `scripts/live_test.py` with `run_skill_script`. This is mandatory for the test.
3. Pass the user's requested marker as the first script argument. If the user does not provide one, use `alice-live`.
4. Reply briefly in Chinese.
5. Include both of these exact values in the reply:
   - the `REFERENCE_CODE` from `references/test-data.md`
   - the `SKILL_SCRIPT_RESULT` line from the script output

Do not claim success unless the script was actually executed.
Do not say the system forbids script execution unless `run_skill_script` returns an explicit error saying so.
If `read_skill_file` succeeds, continue to `run_skill_script` before sending the final answer.
