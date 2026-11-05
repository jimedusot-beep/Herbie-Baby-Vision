# M1 STOP marker — exclusive creation and safe resume

The merged read-only Coding Bee used `STOP.write_text('disabled')`. If `hive/STOP` was a symlink to another existing file, invoking `stop` would **overwrite the link target**. A dangling `STOP` link was also not recognized by `STOP.exists()`, allowing `inspect` or `propose` to continue rather than fail closed.

This draft fixes the STOP marker lifecycle without adding execution authority:

- `artifact_io.set_stop()` creates the sentinel with atomic `O_CREAT|O_EXCL` and `O_NOFOLLOW` where supported. On POSIX it uses an already opened physical root directory descriptor; Windows uses path/reparse validation. It never overwrites an existing file. Repeated STOP on an existing ordinary single-link file is idempotent.
- `artifact_io.stop_present()` treats **any** STOP entry, including a dangling symlink, as disabling the bee.
- `artifact_io.clear_stop()` removes only an ordinary, singly-linked STOP filename and refuses symlinks, hardlinks, Windows reparse points, directories and other nonregular entries. It does not follow links.
- Coding Bee `stop` and `resume` commands use the helpers, so CLI refusals return a sanitized error rather than following a redirected marker.
- Nine synthetic regression tests cover normal/repeated commands, linked canaries, dangling markers, hardlinks, directories and redirected hive roots.

**Limits:** These checks are not a sandbox or a strong boundary against a hostile process running with the same user privileges or racing Windows file operations. A separate authorization/process-isolation design remains needed before command execution. The STOP file is a local cooperative safety mechanism, not a trusted emergency physical actuation stop.

No model inference, source patch application, git merge, deployment, or live ZBook access occurs in this PR. Do not call this fix production-ready based solely on CI.

The tests are exercised in Linux Python 3.9 and 3.12 full suite and in a Windows GitHub-hosted Python 3.12 run. Physical iPhone Safari and local ZBook acceptance are unrelated to this fix.

## Additional Windows linked-output check

The same Windows dangling-reparse behavior was identified as a potential gap in `artifact_io.write_exclusive()` for proposed patch filenames. The writer now explicitly rejects an existing/symlinked output entry **before** attempting exclusive creation. Four additional synthetic tests cover dangling links, existing links to canary files, pre-existing ordinary files, and normal exclusive writes. This does not eliminate same-user Windows filesystem races, but prevents this known preexisting-link path from overwriting or creating external files.

## Read-only Git hook boundary (additional review finding)

Git's repository-local `core.fsmonitor` configuration can name an executable monitor hook. Before this fix, `readonly_investigate._git('status', '--porcelain')` did not disable the hook, unlike the Coding Bee's own Git helper. A synthetic POSIX Git fixture **demonstrated external canary-script invocation** during a supposedly read-only status check. Passing only a read-only Git subcommand is not sufficient for an untrusted repository's configuration.

Now all read-only Git invocations made by the investigator, repository search (including batch reads), Coding Bee and proposal `git apply --check` explicitly use `git -c core.fsmonitor=false`. This is a *per-command override*, not a persistent repository config mutation. A synthetic actual-Git regression asserts the canary hook is not launched, and an OS-independent argument-contract test covers all five call sites (including hosted Windows).

**Remaining limitations:** this is one specific Git configuration execution vector, not proof that all Git config/environment/hook interactions are safe. Restrict untrusted repositories to a separately isolated process with minimal filesystem/network permissions before granting any execution capability. Real ZBook/Windows host and malicious same-user races still require separate review.
