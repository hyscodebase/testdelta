# TestDelta를 만들며 배우는 테스트 검증

2026-11-02 a2 작업 트리에서 전체 테스트 **130개가 64.94초에 통과**했습니다. a3에서는 줄바꿈 없는 diff 회귀 검증까지 추가한 전체 **194개가 92.85초에 통과**했고 Ruff도 통과했습니다. 별도의 고정 사례 50개도 기대 결과와 모두 일치했습니다. 최종 commit 결과는 CI로 확인합니다. 아래의 a1·a2 중간 검증 수치는 당시의 기록입니다. 최종 원격 환경 검증은 해당 commit의 GitHub Actions를 기준으로 확인합니다.

이 문서는 초기 알파 `0.1.0a1`부터 `0.1.0a4`의 Marketplace 게시까지 실제 파일과 실행 결과를 바탕으로 작성했으며, 버전별 검증 이력을 구분합니다. 이전 `0.1.0a1` 검증은 이력으로 남기고, 아직 실행하지 않은 검증과 독자가 직접 해볼 명령은 따로 표시합니다.

2026-11-02의 **a1 이력**에서 로컬 61개 테스트와 초기 commit `9a1ec28`의 GitHub CI 네 조합이 통과했습니다. 이는 현재 a2 전체 matrix의 결과를 대신하지 않습니다. a2 개발 중 한 snapshot에서는 전체 128개 테스트가 65.55초에 통과했고, 이후 추가한 회귀 테스트는 별도로 통과했습니다. 최종 commit의 전체 테스트 수와 matrix 상태는 해당 CI 결과를 확인해야 합니다. 테스트 수는 제품의 실제 저장소 정확도를 뜻하지 않습니다.

추가 리뷰에서는 source hash와 import 경로가 맞아도 unchecked-hash `.pyc` 때문에 이전 코드가 실행될 수 있음을 재현했습니다. `PYTHONDONTWRITEBYTECODE`는 캐시 쓰기만 막으므로 충분하지 않았습니다. `runner/supervisor.py`가 실행마다 새 `PYTHONPYCACHEPREFIX`를 지정하고 `git_inputs.py`가 cache 파일 복사를 제외하도록 수정했습니다. 실제 Git snapshot에 캐시가 추적된 경우도 `tests/test_integration.py`에서 확인합니다.

`adapters/bounded.py`와 `adapters/worker.py`는 Cosmic Ray 계산을 별도 프로세스로 실행합니다. 변이 생성이 오래 걸려도 전체 시간 예산을 소모한 뒤 무제한 계산을 계속하지 않게 하기 위한 경계입니다. source 파싱은 실행과 다르지만 CPU 시간도 예산에 포함됩니다.

## a3에서 기존 PR과 CI를 연결한 방법

기존 PR에 도구 설정이 없으면 `.testdelta.toml`을 과거 commit에 넣기 위해 이력을 다시 만들 필요가 있었습니다. 이제 `init --output`으로 외부 manifest를 만들고 `plan/compare --config`로 선택할 수 있습니다. `git_inputs.py`는 원본 UTF-8 bytes와 SHA-256을 기록합니다. `cli.py`의 replay는 저장된 bytes를 다시 검증하므로 원래 외부 파일을 삭제한 뒤에도 실행할 수 있습니다. 외부 설정을 선택해도 source·helper·의존성·추적된 설정 파일 변경을 허용하지는 않습니다.

GitHub Action은 프로젝트 환경에 TestDelta 의존성을 설치하지 않습니다. `action.yml`이 별도 임시 venv에 도구를 설치하고, 준비된 프로젝트 Python을 `--python`으로 선택합니다. 여기서 venv 실행 파일에 `Path.resolve()`를 쓰면 symlink가 실제 공용 Python으로 바뀌어 venv 의존성을 잃을 수 있어 절대 경로만 만듭니다.

또 다른 경계는 `PYTHONPATH`입니다. 설치된 도구의 site-packages를 통째로 넣으면 프로젝트 Python이 도구 쪽 pytest를 읽을 수 있습니다. `runner/supervisor.py`는 stdlib와 pytest만 사용하는 collector 파일 하나를 실행별 임시 폴더에 복사합니다. 실제로 도구 pytest **9.2.0**, 프로젝트 pytest **8.4.2**를 따로 설치한 실행에서 프로젝트 버전이 사용되고 기록되는 것을 확인했습니다. Action의 소스 설치와 별도 wheel 설치에서도 비교·replay 경로를 실행했습니다.

`compare.py`는 old/new 테스트와 실제 mutation의 unified diff, 전체 diff hash, 잘림 여부를 기록합니다. 마지막 줄바꿈이 없는 파일은 표준 `\ No newline at end of file` 표식을 넣어 삭제·추가 줄이 붙어 보이지 않게 합니다. 각 pytest 실행에는 UTC 시작·종료 시각이 들어갑니다. `plan`의 최대 suite 호출 수는 `6 + 6 × max_mutants`입니다. 기준 검사 4회와 마지막 검사 2회에, 변이마다 최대 3쌍이 필요하기 때문입니다. 시간은 baseline을 실행하기 전에는 알 수 없습니다.

로컬의 상세 report와 bundle에는 진단용 출력과 source가 남습니다. `export.py`의 `build_summary()`는 허용한 상태·개수·상대 경로·hash만 새 dict로 복사합니다. `testdelta export`와 자동 GitHub job summary는 이 제한된 정보만 사용합니다. 예상하지 못한 미래 필드까지 재귀 복사하지 않는 이유는 그 안에 새 private 출력이 들어갈 수 있기 때문입니다. 상대 경로와 hash도 프로젝트를 식별할 수 있어 익명화 보장은 아닙니다.

독립적으로 작성한 개발용 30개와 검증용 20개의 원본 사례는 첫 실행 전에 hash로 고정했습니다. 사람이 지정한 인공 결함을 실제 pytest·반복 검사·최종 control로 확인하는 사례이므로, 자동 Cosmic Ray 생성 품질이나 실제 저장소 정확도와는 구분합니다. 세부 결과와 고정된 입력은 `corpus/README.md`와 `evidence/corpus/`를 기준으로 읽습니다. 첫 실행·재실행 중단과 불일치도 숨기지 않습니다.

네트워크를 차단하는 container 실행 profile과 전체 의존성/OS image의 replay fingerprint는 아직 제공하지 않습니다. 이 알파는 신뢰한 로컬 테스트를 실행하며, 임시 폴더가 sandbox를 뜻하지 않습니다. 고정 benchmark는 10개 실제 Cosmic Ray 변이를 고른 비교를 20회 반복했고, 모두 완료했습니다. 로컬 p95는 **27.697초**, 최대는 **27.963초**였습니다. 준비 시간 제외와 동시 host 부하 등 정확한 범위는 `docs/performance.md`에서 별도로 다룹니다.

## a2에서 실제 저장소를 통해 배운 점

Boltons의 test-only PR 두 건에서 source와 테스트의 원본 내용을 보존하고, 양쪽에 같은 TestDelta manifest를 추가한 로컬 파생 commit으로 실행했습니다. 원본 upstream SHA와 파생 SHA는 `docs/compatibility.md`에 구분했습니다. upstream에 수정이나 연락을 보내지 않았습니다.

- **PR #564:** 기준 검사 네 번과 마지막 원본 코드 검사 두 번은 통과했습니다. 변이 쌍 열 개를 시도했지만 일곱 개는 양쪽 runtime 오류로 미확정, 세 개는 양쪽 통과였습니다. `inconclusive`이며 확정한 탐지 손실은 없습니다.
- **PR #408:** 처음에는 trace를 켠 baseline이 15초 제한을 넘었습니다. 같은 head를 trace 없이 돌린 관찰은 약 0.179초였으므로, 원래 테스트가 느리다는 설명만으로 끝내면 안 됐습니다. `runner/plugin.py`가 대상 줄마다 반복하던 경로 정규화·origin 확인을 캐시하도록 바꿨습니다. 수정 후 old baseline은 약 0.821/0.808초, new baseline은 0.595/0.594초로 기존 제한 안에 들어왔습니다. 이 수치는 해당 로컬 실행의 관찰이지 일반 성능 배수가 아닙니다.
- 수정 후 #408의 변이 쌍 세 개 중 두 개는 양쪽 통과, 한 개는 old collection 오류와 new runtime 오류였습니다. 전체 8.339초 실행의 결과는 여전히 `inconclusive`입니다. timeout을 해결했다고 결과를 clean으로 바꾸면 안 됩니다.

import-origin 검증은 패키지와 직접 module import의 경로 배치를 고려하도록 보완했습니다. 일반 패키지의 child와 우연히 이름이 같은 표준 라이브러리 module을 잘못된 import라고 판정하지 않으면서, 원래 checkout에서 코드를 가져오는 실제 경로 불일치는 계속 탐지해야 합니다. `tests/test_runner.py`의 관련 회귀가 이 경계를 다룹니다.

보고서도 Markdown을 한 덩어리로 보여주던 형태에서 의미별 HTML section·table·펼침 영역으로 바뀌었습니다. `report.py`는 같은 section 데이터로 Markdown과 HTML을 만들고, 판정·완료 여부·시도 수·유효 근거·오류·출처를 나눕니다. source hash뿐 아니라 old/new 테스트 파일 hash도 기록하므로 어떤 내용을 비교했는지 더 정확히 설명할 수 있습니다. 다만 hash는 결과의 정확성을 스스로 증명하지 않습니다.

두 실제 사례는 실행 호환성과 측정 한계를 확인하는 자료입니다. 사용자 수요, maintainer의 제품 채택, Boltons의 결함, TestDelta의 일반 탐지 정확도를 입증하지 않습니다. 자세한 결과와 재현 명령은 [호환성 기록](docs/compatibility.md)에 있습니다.

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
| `src/testdelta/cli.py` | `demo`, `init`, `plan`, `compare`, `replay`, `export` 명령을 연결 | 사용자 입력과 핵심 로직을 나누기 |
| `src/testdelta/git_inputs.py` | commit 파일을 읽고 비교 범위를 결정 | 작업 중인 파일과 검증할 snapshot을 구분하기 |
| `src/testdelta/adapters/cosmic_ray.py` | Cosmic Ray 연산자로 변이를 만들고 ID·hash 기록 | 기존 도구의 검증된 역할을 재사용하기 |
| `src/testdelta/runner/supervisor.py` | pytest subprocess, timeout, 환경과 hash 확인 | 실행 프로그램 바깥에서 상태를 관리하기 |
| `src/testdelta/runner/plugin.py` | pytest hook과 Python trace로 실행 근거 수집 | 종료 코드 하나보다 자세한 증거가 필요한 이유 |
| `src/testdelta/compare.py` | 기준 검사, 변이 실행, 반복 확인, 전체 결과 판정 | 개별 결과와 전체 완료 상태를 분리하기 |
| `src/testdelta/report.py` | 보고서와 종료 코드 생성 | 같은 근거를 여러 출력 형식에서 일관되게 보여주기 |

## 3. Git snapshot을 읽는 이유

`make_plan()`은 base/head를 commit SHA로 확정합니다. 기본 base는 두 revision의 공통 조상인 merge-base이며, `--direct-base`일 때만 정확한 base commit을 사용합니다. 그다음 Git blob을 읽어 파일 내용과 변경 목록을 만듭니다.

여기서 사용자의 현재 작업 폴더를 직접 읽어 비교하지 않는 이유는 검증 대상이 바뀌면 재현하기 어렵기 때문입니다. 아직 commit하지 않은 수정은 결과에 들어가지 않습니다. 기본 manifest는 base commit에서 읽고, `--config`를 지정하면 정확한 외부 bytes를 기록합니다.

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


## Marketplace 게시와 홍보: alpha.4

Marketplace 이름은 기존 GitHub 계정 이름과 겹칠 수 없어 action.yml을 TestDelta Test Quality로 지정했습니다. 제품 브랜드는 TestDelta입니다. Python 배포 버전 0.1.0a4와 SemVer 태그 v0.1.0-alpha.4를 구분합니다. Marketplace 게시 상태는 실제 등록 화면과 공개 listing으로 확인하며, 일반 release가 있다는 사실만으로 Marketplace 등록 완료라고 부르지 않습니다.

등록 초기에는 약관 안내로 게시 체크박스가 잠겨 있었으나, 최종 등록 화면에서 게시 선택이 활성화되고 메타데이터 검증을 통과한 것을 확인했습니다. 마지막 GitHub 본인 재인증은 사용자가 직접 완료했고, 이후 공개 릴리스와 Marketplace 등록을 확인했습니다.

Action 배포 전 검증에서 caller 폴더의 subprocess.py가 bootstrap Python의 표준 모듈을 가릴 수 있음을 확인했습니다. 바깥 실행도 python -I -로 격리하고, mutation worker도 -I에서 도구 경로만 명시적으로 넣습니다. Python의 -I는 pip 설정까지 격리하지 않으므로 도구 설치 환경에서는 PIP_* 변수를 제거하고 PIP_CONFIG_FILE을 os.devnull로 지정합니다. 대상 프로젝트의 의존성은 사용자가 준비한 interpreter에 그대로 두며, CI가 실제 환경 분리와 sentinel 폴더를 확인합니다.

site/는 정적 HTML·CSS·JavaScript 소개 페이지입니다. dev-001의 동결된 입력과 실제 기록을 보여 주며 브라우저에서 pytest를 실행하는 것처럼 표현하지 않습니다. GitHub Pages workflow는 site/만 게시하고, 저장소의 raw 결과나 로컬 DB 보관본을 올리지 않습니다. scripts/check_site.py가 페이지·내부 링크·asset 경로를 검사합니다. 소셜 카드는 원본 SVG와 1200×630 PNG로 제공하며 외부 폰트·tracker를 넣지 않았습니다.

홍보 문구는 docs/launch-kit.md의 한영 초안에 있고, 관측한 유한 사례와 실제 PR 미확정 결과를 구분합니다. 외부 커뮤니티·SNS에 메시지를 보내지 않았습니다. 최종 통과 수와 공개 URL은 해당 commit의 실제 GitHub Actions 및 배포 상태로 확인합니다.

alpha.4 구현 commit 2add31061b995a50a62fbf15b1a28942214f9fce에서 로컬 전체 195개 테스트가 89.49초에 통과했습니다. 원격 네 Python/OS 조합·고정 50개 사례·Ubuntu/macOS native Action·깨끗한 wheel compare/replay가 통과했습니다. 소개 페이지 배포도 성공해 HTML·PNG·근거 JSON이 검토한 파일과 같은 bytes로 제공됨을 확인했습니다. 27.697초 p95는 과거 a3의 고정 측정값으로 유지합니다.

2026-11-03 공개 Marketplace https://github.com/marketplace/actions/testdelta-test-quality 에서 TestDelta Test Quality, v0.1.0-alpha.4, hyscodebase/testdelta 저장소, Testing·Code quality 분류와 실제 설치 snippet을 확인했습니다. 비로그인 HTTP 요청으로도 listing과 릴리스가 200 응답을 반환했습니다. 홈페이지·홍보 ZIP에도 확인된 등록 링크를 반영했으며, 배포 tag는 검증한 55d64056c14834eab99cf49ca86c4786a14804bd를 유지합니다.
