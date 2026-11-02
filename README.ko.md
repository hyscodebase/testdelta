# TestDelta

pytest 테스트를 바꾼 뒤, 이전에 잡던 결함을 놓치게 되었는지 확인합니다.

**초기 알파 — `0.1.0a1`.** 같은 production code와 같은 변이 집합에 변경 전후 테스트를 실행합니다. 이전 테스트는 실패하고 새 테스트는 통과하는 구체적인 변이를 검토 근거로 남깁니다.

[English](README.md) · [1인 개발 로드맵](docs/solo-roadmap.md) · [학습 문서](STUDY.MD) · [기여 안내](CONTRIBUTING.md)

이 결과는 해당 PR이 잘못되었다는 판정이 아닙니다. 의도적으로 보장 범위를 바꾸는 경우도 있습니다. 탐지 손실이 없다는 결과도 실행한 유한한 변이·테스트 범위만 설명합니다.

## 실제 실행 데모

Python 3.11–3.13, Git, [uv](https://docs.astral.sh/uv/)가 필요합니다. 현재 저장소에서 설치하며 PyPI 배포가 완료되었다고 가정하지 않습니다.

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
uv sync --extra dev
uv run testdelta demo
```

데모는 직접 만든 작은 가격 계산 함수와 두 테스트 버전으로 임시 Git 저장소를 만듭니다. 원래 코드에서는 두 테스트 모두 통과하지만, 두 번째 테스트는 정확한 값 비교를 약한 비교로 바꿉니다. Cosmic Ray 변이를 만들고 pytest를 실제 실행합니다. 모델이나 API key, LLM judge가 필요하지 않습니다.

`.testdelta/demo/report.html`에서 결과를 읽고 `report.json`에서 상세 실행 근거를 확인합니다. 합성 Git 저장소는 출력 폴더 안에 보존되며 정확한 경로가 `demo_repository`에 기록됩니다. 이 경로를 `replay --repo`에 사용할 수 있습니다. bundle 자체에 전체 저장소가 포함되는 것은 아닙니다.

다음 세 합성 시나리오를 실행할 수 있습니다.

```bash
uv run testdelta demo --scenario lost --output .testdelta/demo-lost
uv run testdelta demo --scenario refactor --output .testdelta/demo-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/demo-inconclusive
```

각각 탐지 손실, 정상적인 테스트 리팩터링, 유효하지 않은 baseline을 보여줍니다. `demo`는 기대한 시나리오 판정을 관찰하면 종료 코드 `0`을 반환하므로, 의도한 미확정 예제도 `0`일 수 있습니다. 보고서의 판정과 완료 상태를 함께 읽으세요. 이는 `compare`의 종료 규칙과 다르며 실제 프로젝트 성능 측정도 아닙니다.

## 자기 저장소에 적용하기

먼저 **비교할 테스트 변경보다 앞선 commit**에 `.testdelta.toml`을 넣습니다. 아래 예시는 TestDelta checkout에서 옆 디렉터리의 프로젝트를 가리킵니다.

```bash
uv run testdelta init --repo ../your-project \
  --source src/pricing.py --tests tests/test_pricing.py
```

생성되는 manifest:

```toml
source_modules = ["src/pricing.py"]
test_paths = ["tests/test_pricing.py"]
```

manifest를 프로젝트에 commit한 뒤 테스트 변경을 별도 commit합니다. `main`이 변경 전 기준 revision인 예시입니다.

```bash
uv run testdelta plan --repo ../your-project --base main --head HEAD
uv run testdelta compare --repo ../your-project --base main --head HEAD \
  --output .testdelta/review --budget-seconds 120 --max-mutants 10
```

`plan`은 Git에 commit된 파일을 읽고 지원 범위를 확인하며 테스트를 실행하지 않습니다. 기본 기준은 두 revision의 공통 조상인 merge-base입니다. 정확한 base commit과 비교하려면 `--direct-base`를 사용합니다. commit하지 않은 변경은 비교하지 않습니다.

`compare`는 프로젝트의 테스트를 실행합니다. TestDelta를 실행하는 Python 환경에 대상 프로젝트의 의존성이 있어야 하며 자동 설치하지 않습니다. 초기 실행기는 외부 pytest plugin 자동 로드를 끄고 상속하는 환경 변수를 제한하므로 해당 기능에 의존하는 프로젝트는 호환되지 않을 수 있습니다.

첫 범위는 명시한 Python source 파일이 그대로이고 선택한 테스트 파일만 바뀐 경우입니다. source, manifest, helper, `conftest.py`, 의존성 파일, 설정 등 다른 파일이 바뀌면 지원하지 않는 비교로 표시합니다. 변경이 없는 비교도 지원 대상이 아닙니다.

## 네 가지 실행 결과를 비교합니다

| | 원래 production code | 동일한 변이를 적용한 code |
|---|---|---|
| 이전 테스트 | 통과해야 함 | 변이 줄에 도달한 assertion 실패 |
| 새 테스트 | 통과해야 함 | 통과하면 해당 변이를 놓친 것 |

원본 코드 기준 검사는 각 테스트 버전에서 두 번 실행합니다. 탐지 손실 후보는 old/new 쌍이 세 번 일치하는지 확인하고, 마지막에 원본 코드 기준 검사를 다시 합니다. 반복 확인이 모든 flaky test를 제거한다는 뜻은 아닙니다.

import·collection·fixture·runtime 오류나 timeout을 결함 탐지 성공으로 세지 않습니다. 실행 전후 source hash와 실제 import 경로를 확인하고 도달한 줄을 기록합니다. 초기 실행기에서는 skip 또는 xfail이 하나라도 있으면 완전한 실행으로 보지 않습니다.

변이 연산자는 Cosmic Ray 라이브러리의 일부를 사용합니다. 새 범용 mutation engine을 만드는 프로젝트가 아니며, 모든 버그나 의미가 같은 변이까지 완전히 다루지 않습니다.

## 결과와 종료 코드

| 결과 | 의미 | 종료 코드 |
|---|---|---:|
| `no_loss_observed` | 선택한 비교가 완료되었고 확정한 탐지 손실 없음 | `0` |
| `loss_observed` | 비교가 완료되었고 반복 확인한 탐지 손실 있음 | `1` |
| `incomplete_with_witnesses` | 일부 근거가 있지만 전체 비교는 미완료 | `2` |
| `inconclusive` / `unsupported_change` | 유효한 비교를 완료할 수 없음 | `2` |
| 입력·실행 준비 오류 | 명령을 준비하거나 완료할 수 없음 | `3` |

`--advisory`는 완전한 `loss_observed` 실행의 종료 코드만 `0`으로 바꿉니다. 보고서의 탐지 손실은 남고 미완료·지원 불가 결과는 성공으로 바뀌지 않습니다. `demo`는 위에서 설명한 별도 종료 규칙을 사용합니다.

`--max-mutants`는 선택할 변이 수, `--budget-seconds`는 비교 시간, `--timeout-seconds`는 개별 테스트 실행 시간을 제한합니다. 선택한 변이를 모두 실행해도 전체 프로그램에 대한 완전한 분석은 아닙니다. 시간이 부족해 작업이나 기준 검사를 마치지 못하면 깨끗한 결과로 표시하지 않습니다.

## 보고서와 재실행

출력 폴더에는 `report.html`, `report.md`, `report.json`, `bundle.json`, `bundle.sha256`이 생성됩니다. 실제 저장소를 보존한 비교에서는 보고서의 witness ID를 골라 재실행할 수 있습니다.

```bash
uv run testdelta replay .testdelta/review --witness WITNESS_ID \
  --repo ../your-project --output .testdelta/replay
```

기록된 commit과 같은 supervisor 환경·실제 대상 Python/pytest runtime이 필요합니다. 이 기록은 전체 의존성과 운영체제 이미지를 완전히 식별하지는 않습니다. bundle에는 전체 저장소와 의존성이 들어 있지 않습니다. checksum은 우발적인 변경을 확인하며 작성자의 신원을 인증하는 서명은 아닙니다.

보고서는 로컬에 저장됩니다. `GITHUB_STEP_SUMMARY`가 있으면 Markdown 결과를 GitHub Actions job summary에도 덧붙입니다. 별도의 hosted dashboard나 자동 PR 코멘트 기능은 없습니다. 공유 전 source와 실행 출력에 공개하면 안 되는 정보가 없는지 확인하세요. [CI 통합 예시](docs/ci.md)도 참고할 수 있습니다.

## 기존 도구와 범위

같은 변이로 변경 전후 테스트를 비교하는 방식은 이미 존재합니다. [testtruth](https://github.com/T4LEL/testtruth)는 JS/TS에서 이 흐름을 제공하고, [Assertiva](https://github.com/Soturine/Assertiva)는 Python을 포함한 baseline/candidate 변이 근거를 제공합니다. [TestSeal](https://github.com/satwiksps/testseal)은 테스트 약화 신호를 정적으로 검사합니다. [Cosmic Ray](https://github.com/sixty-north/cosmic-ray)는 TestDelta가 사용하는 변이 연산자를 제공합니다.

TestDelta는 작은 pytest 검토 흐름을 실험하는 도구입니다. 알고리즘의 신규성, 더 넓은 지원 범위, 더 높은 정확도를 주장하지 않습니다. 기존 도구로 충분하다면 그것을 사용해도 좋습니다.

CI 대상은 Ubuntu의 Python 3.11·3.12·3.13과 macOS의 Python 3.13입니다. 선언된 matrix 자체가 검증 결과는 아니므로 사용하는 commit의 [CI 결과](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml)를 확인하세요. Windows, source와 test를 함께 바꾸는 migration, symlink/submodule, 외부 서비스, 임의의 monorepo는 초기 범위 밖입니다. snapshot은 파일별 5 MB, 전체 25 MB 제한이 있습니다.

임시 폴더는 운영체제 sandbox가 아닙니다. 자신의 계정 권한으로 실행해도 신뢰할 수 있는 테스트에만 사용하세요. 자세한 실행 경계는 [SECURITY.md](SECURITY.md)에 있습니다.

## 개발

```bash
uv run pytest
uv run ruff check .
uv run python -m build --wheel
```

[STUDY.MD](STUDY.MD)는 실제 구현과 확인한 결과, 직접 해볼 실습을 구분해 설명합니다. 작은 fixture·버그 재현·문서 개선을 환영합니다.

MIT © 2026 Hong Yuseok. [LICENSE](LICENSE).
