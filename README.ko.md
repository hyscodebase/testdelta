# TestDelta

**테스트는 여전히 통과합니다. 이전에 잡던 결함도 계속 잡을까요?**

[![CI](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml/badge.svg)](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml)

TestDelta는 **pytest 테스트만 바뀐 PR**을 검토하는 GitHub Action과 CLI입니다. 동일한 production code와 동일한 변이에 변경 전후 테스트를 실행해, 이전 테스트는 잡지만 새 테스트는 놓치는 구체적인 결함을 보여줍니다.

테스트 리팩터링, assertion 변경, 코딩 에이전트가 수정한 테스트를 검토할 때 사용할 수 있습니다. **LLM, API key, 별도 서비스 계정이 필요하지 않습니다.**

[English](README.md) · [Action 사용법](docs/action.md) · [검증 현황](docs/quality-status.md) · [호환성](docs/compatibility.md) · [기여 안내](CONTRIBUTING.md)

**초기 알파:** 명시한 Python source/test 파일, Ubuntu/macOS, Python 3.11–3.13을 대상으로 합니다. 실행한 유한한 비교의 근거를 제공하며, PR 전체의 정확성이나 안전성을 판정하지 않습니다.

## 테스트만 바뀐 PR에 추가하기

먼저 프로젝트의 실제 tracked 파일 경로로 `.testdelta.toml`을 만들고, **검사할 테스트 변경보다 앞선 commit**에 넣습니다.

```toml
source_modules = ["src/pricing.py"]
test_paths = ["tests/test_pricing.py"]
```

아래 workflow도 테스트 변경 PR을 열기 전에 추가합니다. 예시는 pytest 외의 의존성이 없는 프로젝트용입니다. 필요한 경우 설치 단계를 프로젝트의 고정된 테스트 환경 구성으로 바꾸세요.

```yaml
name: TestDelta
on:
  pull_request:
    paths: ["tests/**"]
permissions:
  contents: read
jobs:
  compare:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
        with:
          python-version: "3.13"
      - run: python -m pip install "pytest==8.4.2"
      - name: Compare test revisions
        id: testdelta
        uses: hyscodebase/testdelta@dae67c6d6b44bc4d3ceda51b4188c6ad8801efee
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          python: python
          max-mutants: "10"
          budget-seconds: "120"
```

Action은 별도 도구 환경에 TestDelta를 설치하고, 프로젝트 테스트에는 준비된 Python을 사용합니다. GitHub 작업 요약과 로컬 HTML/JSON 보고서를 만듭니다. PR 댓글이나 artifact를 자동으로 게시하지 않습니다. [전체 입력·출력 설명 →](docs/action.md)

이미 열린 PR에는 `config: path/to/reviewed-policy.toml`로 **외부 manifest**를 지정할 수 있습니다. Git 이력을 바꿀 필요가 없습니다. 이 파일은 검사 범위를 결정하는 신뢰한 정책이어야 합니다. 검토된 workflow에서 관리하거나 신뢰한 base revision에서 가져오세요. 검토하지 않은 PR이 스스로 검사 범위를 정하게 하지 마세요. 정확한 설정 내용과 hash는 replay에 기록되며, 외부 설정을 써도 지원하는 변경 범위는 같습니다.

선택한 테스트 파일만 바뀌어야 합니다. production source, helper, `conftest.py`, 의존성, 설정, 저장소 내부 manifest가 함께 바뀌면 지원하지 않는 비교입니다. workflow의 경로 필터가 이 규칙을 바꾸지는 않습니다. 외부 pytest plugin 자동 로드는 꺼져 있으므로 작은 호환 가능한 테스트부터 시작하세요.

테스트는 runner 사용자의 파일·네트워크 권한으로 실행됩니다. 임시 폴더는 **sandbox가 아닙니다**. 일반 테스트 작업과 같은 신뢰 정책을 적용하고, 권한이 높은 `pull_request_target`에서 신뢰하지 않은 PR 코드를 실행하지 마세요. [보안 설명 →](SECURITY.md)

## 로컬 데모 실행

Git, Python 3.11–3.13, [uv](https://docs.astral.sh/uv/)가 필요합니다.

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
git checkout dae67c6d6b44bc4d3ceda51b4188c6ad8801efee
uv sync
uv run testdelta demo --scenario lost
```

`.testdelta/demo/report.html`을 여세요. 합성 가격 계산 예제는 `total(1000, 3) == 3500` 같은 정확한 assertion을 `total(1000, 3) >= 0`으로 바꿉니다. 원래 코드에서는 둘 다 통과하지만, 선택한 결함을 넣으면 약해진 테스트가 놓치는 동작이 드러납니다. 보고서에서 실제 변이, 테스트 diff, 반복 실행, source/test hash를 확인할 수 있습니다.

정상적인 리팩터링과 유효하지 않은 baseline도 실행할 수 있습니다.

```bash
uv run testdelta demo --scenario refactor --output .testdelta/demo-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/demo-inconclusive
```

`demo`는 기대한 판정을 관찰하면 `0`으로 종료합니다. 의도한 미확정 시나리오도 여기에 해당하므로 보고서의 판정과 완료 상태를 읽어야 합니다. 이 합성 예제들은 실제 프로젝트 benchmark가 아닙니다.

## 기존 변경을 로컬에서 비교하기

TestDelta checkout에서 프로젝트의 commit을 지정합니다.

```bash
uv run testdelta init --source src/pricing.py --tests tests/test_pricing.py \
  --output .testdelta/project.toml
uv run testdelta plan --repo ../your-project --base main --head HEAD \
  --config .testdelta/project.toml
uv run testdelta compare --repo ../your-project --base main --head HEAD \
  --config .testdelta/project.toml --python ../your-project/.venv/bin/python \
  --output .testdelta/review --budget-seconds 120 --max-mutants 10
```

source/test 경로를 바꾸고 프로젝트 Python에 pytest와 필요한 의존성을 준비하세요. `plan`은 commit된 Git snapshot만 읽고 테스트는 실행하지 않습니다. `compare`는 테스트를 실행합니다. 기본 기준은 두 revision의 merge-base이며, 정확한 base commit을 쓰려면 `--direct-base`를 지정합니다. commit하지 않은 변경은 제외됩니다. 외부 config 경로는 `--repo`와 별개로 현재 작업 폴더 기준입니다.

## 결과 읽기

| 판정 | 의미 | 종료 코드 |
| --- | --- | ---: |
| `no_loss_observed` | 선택한 비교를 완료했으며 확정한 탐지 손실 없음 | `0` |
| `loss_observed` | 선택한 비교를 완료했고 탐지 손실 확인 | `1` |
| `incomplete_with_witnesses` | 확정한 일부 근거가 있으나 전체 비교는 미완료 | `2` |
| `inconclusive` / `unsupported_change` | 유효한 비교를 완료하지 못함 | `2` |
| 입력·실행 오류 | 작업을 준비하거나 완료하지 못함 | `3` |

Action의 `advisory: "true"`나 CLI의 `--advisory`는 **완료된** 탐지 손실만 종료 코드 `0`으로 바꿉니다. 미완료 비교는 여전히 실패합니다.

탐지 손실을 확정하려면 먼저 원본 코드에서 두 테스트 버전이 각각 두 번 통과해야 합니다. 같은 변이에서 이전 테스트는 변경된 줄에 도달해 assertion에 실패하고 새 테스트는 통과해야 합니다. 이 결과가 세 쌍에서 반복되고 마지막 원본 코드 검사도 통과해야 합니다. collection·fixture·runtime·import 오류와 timeout은 결함 탐지 성공으로 세지 않습니다. skip/xfail도 미완료로 남깁니다.

변이는 [Cosmic Ray](https://github.com/sixty-north/cosmic-ray)의 일부 연산자로 생성합니다. 정해진 상한까지 선택한 변이는 모든 버그를 포괄하거나 통계적으로 대표하지 않습니다. 보장 범위를 의도적으로 줄인 변경일 수도 있으므로 구체적인 근거를 보고 판단하세요.

## 근거 보관과 공유

실행마다 `report.html`, `report.md`, `report.json`과 replay bundle을 만듭니다. 시도한 변이 쌍과 유효한 근거를 구분합니다. Replay에는 기록된 commit과 일치하는 기록된 runtime이 필요하며, bundle이 독립적인 환경 image는 아닙니다.

```bash
uv run testdelta export .testdelta/review --output .testdelta/share.json
```

Export와 자동 작업 요약에는 raw log, source/config 원문, 절대 runtime 경로가 포함되지 않습니다. 상대 경로·revision·결과는 남으므로 공유 전에 확인하세요. 원본 보고서와 bundle에는 source code나 캡처한 출력이 있을 수 있습니다. [보고서와 replay 설명 →](docs/report-format.md)

## 확인한 범위

| 근거 | 확인한 내용 |
| --- | --- |
| [a3 시점 로컬 테스트 194개](STUDY.MD) | 해당 구현 테스트 실행 통과. 사용할 commit의 [CI 결과](https://github.com/hyscodebase/testdelta/actions)는 별도로 확인 |
| [고정 사례 50개](corpus/README.md) | 직접 작성한 control로 개발 30개·검증 20개의 기대 판정과 일치. 일반 정확도나 자동 변이 품질 측정은 아님 |
| [로컬 실행 시간 20회](docs/performance.md) | macOS 한 대의 합성 가격 계산 예제, 매회 변이 10개에서 p95 **27.697초**. 준비 시간 제외, host 부하 미통제 |
| [Boltons의 고정 PR 2개](docs/compatibility.md) | 둘 다 **미확정**. 실행 오류를 보존했으며 확정한 탐지 손실이나 clean 결과 없음 |

AI가 만든 테스트에 대한 탐지 성능, 외부 도입, 임의 프로젝트의 실행 속도는 측정해 입증하지 않았습니다. source와 test가 함께 바뀌는 PR, Windows, plugin 의존 suite, 임의의 monorepo, 네트워크 격리 실행은 초기 지원 범위 밖입니다. [상세 검증 현황 →](docs/quality-status.md)

## 관련 프로젝트와 기여

같은 변이로 변경 전후를 비교하는 아이디어는 이미 존재합니다. [testtruth](https://github.com/T4LEL/testtruth)는 JS/TS, [Assertiva](https://github.com/Soturine/Assertiva)는 Python을 포함한 baseline/candidate 근거를 다룹니다. [TestSeal](https://github.com/satwiksps/testseal)은 테스트 약화 신호를 정적으로 검사합니다. TestDelta는 명시적인 pytest 작업 흐름과 개별 실행 근거에 집중하며, 새로운 알고리즘이나 다른 도구보다 높은 정확도를 주장하지 않습니다.

작은 재현 사례, 호환성 fixture, 문서 개선을 환영합니다. [기여 안내](CONTRIBUTING.md), [학습 문서](STUDY.MD), [코딩 에이전트 검토 흐름](docs/agent-workflow.md)을 참고하세요.

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python -m build --wheel
```

MIT © 2026 Hong Yuseok. [라이선스](LICENSE).
