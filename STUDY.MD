# TestDelta를 만들며 배우는 테스트 검증

이 문서는 초기 알파 `0.1.0a1`의 실제 파일과 첫 실행 결과를 바탕으로 작성했습니다. 아직 실행하지 않은 검증과 독자가 직접 해볼 명령은 따로 표시합니다.

## 1. 무엇을 만들었나

테스트를 고친 뒤에도 모든 테스트가 통과한다고 가정해 봅시다. 이전에는 `assert total == 3500`이었는데 새 테스트는 `assert total >= 0`이라면, 여러 잘못된 값도 새 테스트를 통과할 수 있습니다. TestDelta는 이런 차이를 코드의 겉모양만 보고 판단하지 않고, 동일한 인공 결함을 두 테스트 버전에 적용해 실행 근거를 모읍니다.

인공 결함을 넣은 코드 버전을 **변이(mutant)**라고 합니다. 예를 들어 덧셈을 뺄셈으로 바꾼 코드입니다. 테스트가 이 변이에서 assertion 실패를 내면 해당 변이를 탐지했다고 표현합니다. 변이가 살아남았다고 해서 원래 코드에 실제 버그가 있다는 뜻은 아닙니다.

TestDelta의 첫 범위는 production source가 그대로이고 선택한 pytest 테스트 파일만 바뀌는 경우입니다. 소스와 테스트를 함께 바꾸면 결과의 차이가 무엇 때문인지 설명하기 어려우므로 초기 구현에서 지원하지 않습니다.

## 2. 전체 데이터 흐름

```text
Git base/head commit + .testdelta.toml
    ↓
변경 파일 확인, 지원 범위와 source hash 기록
    ↓
같은 source에 old tests / new tests 구성
    ↓
원본 코드 기준 검사
    ↓
Cosmic Ray로 선택한 동일 변이를 양쪽에 적용
    ↓
pytest 실행 + import 경로·도달 줄·실패 종류 수집
    ↓
탐지 손실 반복 확인 + 마지막 원본 코드 검사
    ↓
JSON/Markdown/HTML 보고서 + replay bundle
```

파일별 역할은 다음과 같습니다.

| 파일 | 역할 | 배울 점 |
|---|---|---|
| `src/testdelta/cli.py` | `demo`, `init`, `plan`, `compare`, `replay` 명령을 연결 | 사용자 입력과 핵심 로직을 나누기 |
| `src/testdelta/git_inputs.py` | commit 파일을 읽고 비교 범위를 결정 | 작업 중인 파일과 검증할 snapshot을 구분하기 |
| `src/testdelta/adapters/cosmic_ray.py` | Cosmic Ray 연산자로 변이를 만들고 ID·hash 기록 | 기존 도구의 검증된 역할을 재사용하기 |
| `src/testdelta/runner/supervisor.py` | pytest subprocess, timeout, 환경과 hash 확인 | 실행 프로그램 바깥에서 상태를 관리하기 |
| `src/testdelta/runner/plugin.py` | pytest hook과 Python trace로 실행 근거 수집 | 종료 코드 하나보다 자세한 증거가 필요한 이유 |
| `src/testdelta/compare.py` | 기준 검사, 변이 실행, 반복 확인, 전체 결과 판정 | 개별 결과와 전체 완료 상태를 분리하기 |
| `src/testdelta/report.py` | 보고서와 종료 코드 생성 | 같은 근거를 여러 출력 형식에서 일관되게 보여주기 |

## 3. Git snapshot을 읽는 이유

`make_plan()`은 base/head를 commit SHA로 확정합니다. 기본 base는 두 revision의 공통 조상인 merge-base이며, `--direct-base`일 때만 정확한 base commit을 사용합니다. 그다음 Git blob을 읽어 파일 내용과 변경 목록을 만듭니다.

여기서 사용자의 현재 작업 폴더를 직접 읽어 비교하지 않는 이유는 검증 대상이 바뀌면 재현하기 어렵기 때문입니다. 아직 commit하지 않은 수정은 결과에 들어가지 않습니다. `.testdelta.toml`도 base commit에 있어야 합니다.

```toml
source_modules = ["src/pricing.py"]
test_paths = ["tests/test_pricing.py"]
```

`source_modules`는 외부 CLI 계약상 추적되는 Python 파일을 명시합니다. 변이 adapter 자체에는 디렉터리를 펼치는 기능이 있지만, 이것을 곧바로 manifest가 디렉터리를 지원한다는 뜻으로 읽으면 안 됩니다. 공개 입력 검증과 내부 함수의 기능 범위는 다를 수 있습니다.

변경 파일이 선택한 테스트 범위 밖이면 `unsupported_change`로 남깁니다. `conftest.py` 같은 fixture 설정도 제외합니다. 비교 조건을 정확히 지키는 것이 초기 지원 범위를 넓히는 것보다 중요하기 때문입니다.

`git archive` 대신 blob을 읽는 이유도 같습니다. `.gitattributes`의 `export-ignore`가 변경된 파일을 숨기면 “테스트만 바뀌었다”는 잘못된 판단을 할 수 있습니다. 이 상황을 다루는 검증이 `tests/test_git_inputs.py`에 있습니다.

## 4. 같은 변이를 어떻게 보장하나

`generate_mutations()`는 Cosmic Ray의 연산자를 사용합니다. 무작위 변수 교체처럼 이번 범위에 맞지 않는 연산자는 제외하고, 경로·위치·연산자 순서를 정해 변이를 고릅니다. 소스 파일을 import하거나 실행하지 않고 구문을 분석합니다.

각 변이에는 다음과 같은 기록이 들어갑니다.

- 어느 source 파일의 몇 번째 줄인지.
- 어떤 Cosmic Ray 연산자와 버전으로 생성했는지.
- 원본 source hash와 변이 source hash.
- 원본·변이 source, occurrence, 안정적인 변이 ID.

**hash**는 내용에서 계산하는 고정된 식별값입니다. 같은 내용인지 확인하는 데 유용하지만 누가 파일을 만들었는지를 인증하지는 않습니다. `bundle.sha256`도 서명이 아니라 우발적인 내용 변경을 확인하는 checksum입니다.

`tests/test_mutations.py`는 입력 순서를 바꿔도 결과가 같은지, 원본 파일을 바꾸지 않는지, 경로가 작업 공간을 벗어나지 않는지, source를 import하지 않는지 등을 검증하도록 작성되어 있습니다. 검증 코드를 작성했다는 사실과 실제 통과 결과는 구분해야 합니다.

## 5. pytest 실패를 모두 탐지 성공으로 세면 안 되는 이유

프로그램이 실패했다는 사실만으로 변이를 제대로 검증했다고 말할 수 없습니다. 테스트 파일 import가 실패했거나 fixture 준비에 실패해도 pytest는 실패 종료합니다. 이를 “변이를 잡았다”고 세면 측정값이 부풀려집니다.

실행기는 다음 상태를 나눕니다.

| 상태 | 의미 |
|---|---|
| `pass` | 선택한 테스트가 실행되고 통과 |
| `assertion_failure` | 테스트 본문의 assertion 또는 pytest 실패 |
| `collection_error` | 테스트를 수집하는 단계에서 실패 |
| `fixture_error` | 테스트 준비·정리 단계에서 실패 |
| `runtime_error` | 일반 실행 오류 또는 내부 오류 |
| `timeout` | 정한 시간 안에 실행이 끝나지 않음 |
| `not_executed` | 테스트 미실행, 누락, skip/xfail 등 |
| `invalid_evidence` | hash·import 경로·수집 근거를 신뢰할 수 없음 |

`compare.py`는 `assertion_failure`이면서 변이 줄에 도달한 경우만 `killed`로 분류합니다. 새 테스트가 source를 아예 사용하지 않아도 정상 실행을 끝냈다면 `survived`일 수 있습니다. 이것이 실제 탐지 범위 감소일 수 있기 때문입니다.

plugin은 실제 import한 파일 경로도 기록합니다. 변이 파일을 만들어 놓고 실수로 설치된 원래 패키지를 import했다면, 변이를 시험한 것처럼 보이지만 실제로는 다른 코드를 실행한 것입니다. 경로 검증은 이런 오해를 줄입니다.

다만 프로젝트 테스트는 신뢰할 수 있는 코드라고 가정합니다. 악의적인 테스트가 trace를 방해하거나 근거 파일을 조작하는 공격까지 막는 sandbox는 아닙니다. 자세한 경계는 `SECURITY.md`에 있습니다.

## 6. 네 칸과 반복 확인

| | 원본 코드 | 변이 코드 |
|---|---|---|
| 이전 테스트 | 통과 | 변이를 탐지하는지 확인 |
| 새 테스트 | 통과 | 같은 변이를 탐지하는지 확인 |

원본 코드에서 이미 테스트가 실패한다면 변이 때문에 실패했는지 알 수 없습니다. 따라서 두 테스트 버전 모두 원본 코드 기준 검사를 통과해야 합니다. 현재 구현은 각 버전에서 이를 두 번 확인합니다.

이전 테스트는 변이를 잡고 새 테스트는 통과하면 탐지 손실 후보입니다. 첫 실행을 포함해 세 old/new 쌍이 일치하는지 확인한 뒤, 마지막에 원본 코드 기준 검사를 다시 실행합니다. 이 과정은 단순한 일시 실패를 줄이지만 통계적으로 모든 flakiness를 배제하지는 않습니다.

전체 비교가 완료되었는지와 witness가 있는지는 서로 다른 정보입니다. 일부 변이를 검증했지만 시간 제한으로 나머지를 끝내지 못했다면 `incomplete_with_witnesses`가 될 수 있습니다. 근거가 조금 있다는 이유로 전체 작업이 성공했다고 표시하지 않습니다.

`--advisory`도 같은 원칙을 지킵니다. 완전한 비교에서 탐지 손실이 발견된 경우 CI 종료 코드만 완화하며, 미완료 결과를 성공으로 바꾸지 않습니다.

## 7. 확인한 첫 실행과 아직 구분할 검증

2026-11-02 초기 구현에서 직접 생성한 합성 pricing fixture를 실제 pytest로 실행한 보고서를 확인했습니다.

| 항목 | 첫 실행에서 관찰한 값 |
|---|---|
| TestDelta | `0.1.0a1` |
| 환경 | macOS ARM64, Python `3.13.5` |
| pytest / Cosmic Ray | `9.2.0` / `8.7.0` |
| 결과 | `loss_observed`, `complete: true` |
| 선택한 변이 / 완료한 변이 | `6 / 6` |
| 확인한 witness | `6` |

이것은 의도적으로 assertion을 약하게 만든 자체 예제에서 비교 흐름이 작동한 근거입니다. 실제 저장소에서의 정확도, 모든 Python 버전 지원, 일반적인 실행 속도, 기존 도구 대비 우수성을 증명하지 않습니다.

이후 같은 구현에서 정상 refactor 시나리오는 6개 변이를 완료하고 `no_loss_observed`, invalid baseline 시나리오는 변이를 실행하기 전에 `inconclusive`가 되는 것도 확인했습니다. 현재 `demo`는 합성 Git 저장소를 출력 폴더에 보존하고 `demo_repository`에 경로를 기록합니다. 이전 첫 실행과 달리 이 저장소 경로로 witness를 replay할 수 있습니다.

실행 기록에는 supervisor의 환경뿐 아니라 실제 자식 프로세스의 Python·pytest 버전과 실행기 경로인 `target_runtime`도 들어갑니다. 이를 비교해 다른 실행기를 같은 환경으로 오해하는 일을 줄이지만, 전체 의존성의 완전한 fingerprint는 아닙니다. runner의 24개 pytest 통합 검증이 통과한 결과도 확인했습니다. 전체 패키지와 모든 CI matrix의 성공을 의미하지는 않습니다.

처음 로컬 개발 환경에서는 Python이 숨김 속성이 붙은 editable-install `.pth` 파일을 읽지 않아 import가 실패하는 문제가 있었습니다. 개발 단계의 실행은 `PYTHONPATH=src`로 source를 명시해 확인했습니다. 이는 runner의 검증 결과와 별개의 설치 환경 문제이며, 일반 사용자는 README의 설치 명령과 CI의 wheel 검증 결과를 기준으로 판단해야 합니다.

CI workflow는 Ubuntu Python 3.11·3.12·3.13, macOS Python 3.13에서 lint·pytest·wheel build·새 환경의 wheel demo를 실행하도록 작성했습니다. **workflow 파일을 작성한 것만으로 모든 matrix가 통과했다고 말하지 않습니다.** 실제 commit의 GitHub Actions 결과를 확인해야 합니다.

## 8. 직접 해볼 명령

다음은 사용자가 실행해 볼 명령입니다. 설치가 끝난 TestDelta checkout에서 실행합니다.

```bash
uv run testdelta demo --output .testdelta/my-demo
uv run testdelta demo --scenario refactor --output .testdelta/my-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/my-inconclusive
uv run pytest
uv run ruff check .
uv run python -m build --wheel
```

예상 결과: 기본 demo의 합성 예제에서는 탐지 손실을 찾고 JSON과 HTML 보고서를 만듭니다. 다른 시나리오는 정상 refactor와 baseline 미확정 결과를 보여줍니다. `demo`의 종료 코드 `0`은 기대한 시나리오가 관찰되었다는 의미이므로 보고서의 `complete`와 `verdict`를 함께 확인해야 합니다. 테스트·lint·build 결과는 사용 중인 commit과 환경에서 직접 확인해야 합니다.

보고서를 읽을 때는 다음을 찾아보세요.

1. `complete`와 `verdict`가 각각 무엇을 뜻하는가.
2. 동일 witness에서 old/new가 왜 다른 결과를 냈는가.
3. 실행 중인 source가 정말 변이를 적용한 파일인지 어떻게 확인하는가.
4. timeout 또는 baseline 실패가 왜 clean 결과가 될 수 없는가.
5. 같은 mutation ID가 있어도 비교하지 않은 버그까지 설명할 수 없는 이유는 무엇인가.

실제 저장소에서 replay할 때는 저장된 bundle뿐 아니라 기록된 원본 commit과 의존성·환경도 필요합니다. bundle을 self-contained 실행 환경으로 오해하지 마세요.

## 9. 설계에서 남은 선택

현재 구현은 지원 범위를 제한해 잘못된 확신을 줄이는 쪽을 선택했습니다. 그 결과 plugin 의존성이 있거나 source와 테스트가 함께 바뀌는 일반적인 PR 일부를 다루지 못합니다. 이런 사례가 필요하다는 이유만으로 알 수 없는 결과를 pass로 바꾸면 도구의 목적이 사라집니다.

또한 이 비교 방식은 새로운 발명이 아닙니다. testtruth와 Assertiva 등 기존 프로젝트가 관련 기능을 제공합니다. TestDelta를 통해 배우고 개선할 부분은 작은 pytest 흐름, 재현 가능한 근거, 정확한 실패 분류, 사용자가 이해할 수 있는 제한 설명입니다.

다음 개발은 이 기반의 재현성과 설치 안정성을 확인한 뒤 진행합니다. 구체적인 순서는 `docs/solo-roadmap.md`에 있습니다.
