# TestDelta launch kit

These are **unpublished drafts**, ready to copy after the release operator checks the links and the selected commit's CI. Nothing in this file sends messages, creates posts, or requests stars.

## Release facts and destinations

- Project: **TestDelta** — a GitHub Action and CLI for test-only pytest changes.
- Repository and working destination for the drafts: https://github.com/hyscodebase/testdelta
- Action metadata name for the Marketplace submission: **TestDelta Test Quality**.
- Current documented Action pin: `dae67c6d6b44bc4d3ceda51b4188c6ad8801efee`. Update it only after a newer commit is verified.
- Planned next release tag: `v0.1.0-alpha.4`; do not describe this draft as a published release.
- Planned landing page: `https://hyscodebase.github.io/testdelta/`. Confirm deployment before adding it to any post.
- Marketplace listing: pending owner acceptance of GitHub's Developer Agreement and successful publication. Proposed slug `testdelta-test-quality` is **unverified**. Do not announce a live listing or invent its URL.
- The Action can already be used from the repository at the documented commit. Marketplace discovery and Action execution are separate.

Before posting, the release operator checks the actual Pages URL, release/tag, Action pin, Marketplace status, and links. Keep the repository URL in the drafts if a destination remains pending. No interviews, external contacts, or posting are prerequisites for preparing this package.

## Positioning

**English one line**

> TestDelta shows faults that your old pytest tests catch and your changed tests miss.

**한국어 한 줄**

> TestDelta는 pytest 테스트를 수정한 뒤, 이전에 잡던 결함을 놓치게 되었는지 실행 근거로 보여줍니다.

**English elevator pitch**

> Passing tests can hide a weaker assertion. TestDelta compares old and new pytest tests against the same production code and selected mutations. It gives reviewers a concrete fault, the changed-test diff, and repeated execution evidence. It runs as a GitHub Action or local CLI without an LLM API key. The alpha supports explicit test-only changes and keeps incomplete results visible.

**한국어 짧은 소개**

> 테스트를 고친 뒤에도 CI가 초록색이라고 해서 보장 범위가 유지됐다고 단정할 수는 없습니다. TestDelta는 같은 코드와 같은 변이에 이전·새 pytest 테스트를 실행해, 어떤 결함을 놓치게 됐는지 보여줍니다. GitHub Action이나 로컬 CLI로 사용할 수 있고 LLM API key가 필요하지 않습니다. 초기 알파는 명시한 테스트만 바뀐 경우를 다루며, 실행 오류는 미확정으로 남깁니다.

Primary audience: Python maintainers reviewing test refactors and assertion changes. Coding-agent-edited tests are a plausible application; AI-specific detection performance has not been measured. Lead with the concrete review task.

## LinkedIn — English

I built TestDelta to answer a small code-review question:

After changing a test, does it still catch the same faults?

The demo changes an exact price assertion into “the result is nonnegative.” Both test versions pass on the original code. TestDelta applies the same selected mutations to that code and shows where the old tests fail but the new tests pass.

It runs as a GitHub Action or local CLI, with no LLM API key. Reports include the test diff, the actual mutation, and repeated execution evidence. Collection errors and timeouts stay inconclusive.

The alpha supports explicit test-only pytest changes. It could help review test refactors or assertions edited by a coding agent; I haven't measured AI-specific detection performance.

The limits are public too: 50 frozen, hand-authored cases matched their expected outcomes, while both real Boltons PR checks remained inconclusive. Those are bounded checks, not a general accuracy claim.

The README has a pinned Action example and a local demo:
https://github.com/hyscodebase/testdelta

If you try it, a small reproducible case or an unclear report would be useful feedback.

#Python #pytest #OpenSource

## LinkedIn — 한국어

테스트를 바꾼 뒤에도 CI는 초록색인데, 이전에 잡던 결함도 계속 잡고 있을까요?

이 질문을 확인하는 오픈소스 TestDelta를 만들었습니다.

데모에서는 정확한 가격 비교 assertion을 “결과가 0 이상”이라는 조건으로 바꿉니다. 원래 코드에서는 두 테스트 모두 통과합니다. TestDelta는 같은 코드에 같은 변이를 적용해, 이전 테스트는 실패하지만 새 테스트는 통과하는 구체적인 사례를 보여줍니다.

GitHub Action과 로컬 CLI로 실행하며 LLM API key는 필요하지 않습니다. 보고서에는 테스트 diff, 실제 변이, 반복 실행 근거가 담깁니다. 실행 오류나 timeout은 미확정으로 남깁니다.

초기 알파는 명시한 pytest 테스트만 바뀐 PR을 다룹니다. 테스트 리팩터링이나 코딩 에이전트가 바꾼 assertion을 검토할 때 활용할 수 있지만, AI가 작성한 테스트에 대한 별도 성능 측정은 하지 않았습니다.

검증 범위도 공개했습니다. 직접 작성해 고정한 50개 사례는 기대 판정과 일치했고, 실제 Boltons PR 두 건은 모두 미확정이었습니다. 이를 일반적인 정확도로 표현하지 않습니다.

README에 고정 commit 기반 Action 설정과 로컬 데모를 넣었습니다.
https://github.com/hyscodebase/testdelta

작게 재현할 수 있는 호환성 문제나 이해하기 어려운 보고서가 있다면 피드백을 환영합니다.

#Python #pytest #OpenSource

## Short X posts

**English**

Tests still pass. Do they still catch the same faults? TestDelta compares old/new pytest tests on identical mutations and shows lost detection. GitHub Action + CLI, no LLM key. Alpha: test-only changes.
https://github.com/hyscodebase/testdelta

**한국어**

테스트를 바꾼 뒤에도 CI는 초록색. 이전에 잡던 결함도 계속 잡을까요? TestDelta는 같은 변이에 변경 전후 pytest를 실행해 놓친 결함을 보여줍니다. GitHub Action·CLI, LLM key 불필요. 초기 범위는 테스트만 바뀐 PR입니다.
https://github.com/hyscodebase/testdelta

## Show HN

**Title**

Show HN: TestDelta — Do changed pytest tests still catch the same faults?

**URL**

https://github.com/hyscodebase/testdelta

**Body / author comment**

I built a small GitHub Action and CLI for reviewing test-only pytest changes.

The demo weakens exact assertions to “result >= 0.” Both test revisions pass on the original pricing function. TestDelta applies identical selected mutations to unchanged production code, then reports faults the old tests catch and the new tests miss. There is no LLM judge or API key.

A candidate loss must repeat across three old/new execution pairs, with passing original-code baselines and final controls. Collection, fixture and runtime errors, skips, and timeouts don't become successful kills. Incomplete work stays visible.

The scope is deliberately small: explicit Python source/test files, unchanged production code and test configuration, and Ubuntu/macOS with Python 3.11–3.13. Tests execute with host permissions; temporary workspaces aren't a sandbox. The Action uses a separate tool environment and a caller-prepared project interpreter.

The README includes a pinned workflow and a runnable demo. Reports show actual test and mutation diffs, source/test hashes, and execution outcomes. You can export an allowlisted summary or replay a recorded witness with the required repository and runtime.

This isn't a new mutation-testing algorithm. testtruth and Assertiva already offer related before/after workflows; TestDelta reuses Cosmic Ray and explores a focused pytest integration.

The evidence is bounded: all 50 frozen, hand-authored conformance cases matched expectations. Two real Boltons PR checks both remained inconclusive. I don't have evidence of general accuracy or external adoption.

I'd especially appreciate a small compatible test refactor to try, or feedback on what a reviewer needs to understand a concrete lost-detection report. Please avoid sharing private code or raw reports you haven't reviewed.

## Community announcement — English

**Title: TestDelta: review whether a pytest test change loses fault detection**

I made an MIT-licensed GitHub Action and CLI for test-only pytest PRs.

It compares old and new tests on unchanged production code and the same selected Cosmic Ray mutations. When an old test catches a fault and the new test misses it repeatedly, the report shows the concrete mutation and test diff. No LLM API key is needed.

The README includes a pinned workflow and a synthetic demo. This alpha supports explicit Python source/test paths; mixed source changes and plugin-dependent suites are outside the initial scope. Incomplete runs remain inconclusive.

Public checks include 50 finite conformance fixtures and two real PR compatibility checks; both real PR checks were inconclusive. These aren't general accuracy results.

Code, demo, and limitations: https://github.com/hyscodebase/testdelta

Reproducible compatibility reports and feedback on report clarity are welcome.

## 커뮤니티 소개 — 한국어

**제목: pytest 테스트를 수정하면서 결함 탐지력이 줄었는지 확인하는 TestDelta**

테스트만 바뀐 pytest PR을 검토하는 MIT 라이선스 오픈소스를 만들었습니다.

TestDelta는 같은 production code와 같은 Cosmic Ray 변이에 이전·새 테스트를 실행합니다. 이전 테스트가 잡던 결함을 새 테스트가 반복해서 놓치면 실제 변이와 테스트 diff를 보고서로 보여줍니다. LLM API key 없이 GitHub Action이나 CLI로 사용할 수 있습니다.

README에 고정 commit 기반 workflow와 합성 데모가 있습니다. 초기 알파는 명시한 source/test 파일을 대상으로 하며, source도 함께 바뀌거나 외부 plugin에 의존하는 suite는 초기 범위 밖입니다. 실행이 완전하지 않으면 미확정으로 남깁니다.

고정 사례 50개와 실제 PR 두 건의 검증 기록도 공개했습니다. 실제 PR 두 건은 모두 미확정이었으며 일반 정확도를 입증한 결과는 아닙니다.

코드·실행 방법·한계: https://github.com/hyscodebase/testdelta

작은 호환성 재현 사례나 보고서에서 이해하기 어려운 부분에 대한 의견을 환영합니다.

## Concrete 60-second demo recording

This is a recording outline, not a promise that installation or comparison always finishes within 60 seconds. Install beforehand, record an actual run, and label any cuts or time compression. Use only the original synthetic fixtures; don't present them as an upstream bug.

Preparation with the documented pin:

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
git checkout dae67c6d6b44bc4d3ceda51b4188c6ad8801efee
uv sync
uv run testdelta demo --scenario lost --output .testdelta/launch-lost
uv run testdelta demo --scenario refactor --output .testdelta/launch-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/launch-inconclusive
```

| Time | Screen | Narration |
| --- | --- | --- |
| 0–8 s | Actual old/new assertion diff from the lost report | “This exact price check became a nonnegative check. Both pass on the original code.” |
| 8–18 s | The recorded CLI invocation and completed output | “TestDelta runs both revisions against the same selected faults. No model API is involved.” |
| 18–35 s | `.testdelta/launch-lost/report.html`: one actual confirmed witness | “Here is the mutation. The old tests fail an assertion; the new tests pass. The report includes repeated executions and controls.” |
| 35–45 s | Source/test hashes and bounded diffs in that report | “You can review the exact tested revisions and the changed assertion.” |
| 45–53 s | Refactor and inconclusive reports | “A preserved assertion can retain detection. An invalid baseline remains inconclusive.” |
| 53–60 s | README's Action snippet and repository URL | “Start with one trusted test-only pytest change. The README has a pinned Action and a local demo.” |

Use the actual emitted counts and verdicts. If a run is incomplete, show that result or fix the documented setup and rerun; do not edit a report to obtain a desired label. The demo command exits zero for an observed expected scenario, including the deliberately inconclusive one.

Optional Korean narration for the opening and close:

> “정확한 값 비교가 0 이상이라는 비교로 바뀌었습니다. 원래 코드에서는 둘 다 통과하지만, 같은 결함도 계속 잡을까요?”

> “작은 pytest 테스트 변경부터 적용해 보세요. README에 고정 commit 기반 Action 설정과 로컬 데모가 있습니다.”

## Evidence rules for every channel

Use these claims with their scope intact:

| Claim | Supporting artifact | Required scope |
| --- | --- | --- |
| 194 implementation tests passed | [Recorded a3 validation](../STUDY.MD) | Historical local a3 run; later releases need their own CI |
| 50 cases matched expectations | [Frozen corpus](../corpus/README.md) | 30 development + 20 validation, hand-authored controls; not general accuracy or automatic mutation-quality evidence |
| Local p95 27.697 seconds | [Runtime protocol and record](performance.md) | One synthetic pricing fixture, 20 repetitions, 10 mutations each, one macOS host; preparation excluded and load uncontrolled |
| Two real PR checks | [Compatibility report](compatibility.md) | Both inconclusive; no confirmed upstream bug or maintainer endorsement |
| No LLM API key | CLI and Action implementation | Dependencies still need installation; host compute and any CI usage can have costs |

Avoid “100% accurate,” “finds AI bugs,” “first/only,” “production-ready,” “sandboxed,” “guaranteed under two minutes,” or “used by Boltons.” Do not imply Marketplace publication, a verified publisher badge, or Pages availability until each is checked. Do not infer users from stars or downloads.

## Sharing and feedback practice

- Start with the synthetic report and the documented use case. Link to evidence instead of cropping away incomplete results.
- Post once where project announcements are welcome and follow the venue's rules. Do not automate repetitive outreach, tag unrelated maintainers, buy stars, or request reciprocal stars.
- Invite a minimal public reproduction or an allowlisted export. Raw reports/bundles can contain source and logs; review exports too because relative paths and revisions remain.
- A public issue is not permission to use a person's name, logo, quotation, or repository as a testimonial. Ask for explicit opt-in before publishing an attributed case study; no such request has been sent.
- If someone volunteers a case, preserve its revision hashes, supported-scope decision, complete/incomplete status, and their permission for attribution. An inconclusive case is still useful compatibility feedback.
- Keep maintenance feedback separate from popularity: count voluntary repeat use only when it is actually observed. No telemetry or adoption metric is implied by these drafts.
