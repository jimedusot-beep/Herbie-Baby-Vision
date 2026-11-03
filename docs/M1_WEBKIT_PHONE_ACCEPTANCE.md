# M1 mobile WebKit browser verification

Tests the merged public read-only review viewer using a real WebKit browser engine on a GitHub Linux runner, configured with touch and 320/390/430px mobile screens. This is NOT a real iPhone Safari test.

The four tests select all three synthetic fixture files; confirm checksum and report pairing; keep source excerpts and diff hidden until tapped; check 44px button targets; clear evidence; verify narrow screens; render malicious-looking report text as plain text; and refuse mismatched source revisions without exposing the previous patch.

Only the two public static UI files are served from an ephemeral localhost server. The test blocks browser requests to any other origin. No Ollama, gateway, private GitHub source, passwords, real reports, external inference, approvals, patch execution, remote deployment, or repository modification is involved.

The GitHub workflow installs pinned Playwright 1.56.1 and WebKit into a temporary runner directory, and retains a synthetic-fixture-only screenshot as an Actions artifact for seven days. It does not publish a website.

The test proves neither physical iPhone Safari/iCloud Files/VoiceOver nor device performance, and it does not authenticate a report's contents. Human inspection on an actual iPhone and real ZBook Ollama acceptance are still separate milestones. Gateway PR #5 and issue #6 remain untouched.

Run in a configured local Node/WebKit environment with BABY_WEBKIT_PLAYWRIGHT pointing to playwright package: node --test tests/test_m1_mobile_webkit.cjs
