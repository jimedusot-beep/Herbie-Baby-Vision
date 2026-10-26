# Safety and authority boundaries

- Baby Vision may propose code and run approved tests in a disposable checkout; it may not autonomously merge or deploy.
- Do not provide production secrets, hardware ports, live motor connections, camera feeds, or microphone access to coding workers.
- Require human review before merging, deploying, firmware flashing, or changing any hardware-related configuration.
- All H.E.R.B.I.E. motion and facial tracking demonstrations must distinguish simulation from physical hardware.
- Log task scope, commands, code diffs, test results, failures, and approval decisions.
- Fail closed on timeout, missing permissions, test failures, or unavailable safety checks.
- Never claim real hardware or iPad Safari verification from automated simulation alone.
