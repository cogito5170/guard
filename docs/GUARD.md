# GUARD — shadow 뼈대 (CMD-G1)

근거는 baseline `claude/gracious-meitner-vp49xe` 의 다음 문서다.
- BD-07: Guard 는 Policy 와 독립이고, 닫는 쪽으로만 가며, 지금 상태를 읽는다
- BD-20 · BD-24: A0–A8 배분. Validate = A0–A4 · Arbitrate = 선택 · Guard = A5–A8
- BD-23 · BD-76: 목적의 안전 기본 결정
- BD-96 · BD-97: action 계약, 의도가 되지 않는 것
- `SCHEMA_PROPOSAL.md` §2 · `DATA_FLOW.md` §6 · `OPEN_QUESTIONS.md` OQ-17 · 이슈 baseline#7

코드: [`guard/rules.py`](../guard/rules.py) · [`guard/forms.py`](../guard/forms.py) · [`guard/views.py`](../guard/views.py) · [`guard/command.py`](../guard/command.py).

## 1. 흐름

```
evaluate(intent, dc, state, model)
  ├─ validate(intent, dc, model)  A0 꼴 · 이 DC 의 의도인가 · 의도가 되는 행동인가
  │                               A1 문맥이 내놓은 행동인가(+ Model 에 ActionSpec 이 있나)
  │                               A2 결정이 본 실체인가     A3 그 행동의 대상인가     A4 인자가 ActionSpec 과 맞나
  │     └─ 막히면 → GuardResult(DENY, rule = 그 규칙)   GUARD 는 돌지 않는다
  └─ guard(intent, dc, state, model)   걸린 규칙을 모두 본다(논리곱)
        D  DC 가 불완전하거나, 필수 키 · 의도가 쓴 키 가운데 낡은 것이 있는데 위험 등급 행동(목적의 안전 기본 후보는 빼고, BD-103)
        A5 결정이 본 판 ≠ 지금 판 · 지금 상태에 없음
        A6 사전조건이 보는 속성이 지금 없거나 낡음 · 지금 거짓 · 대상 모형이 다름
        A7 external · irreversible 인데 허가 없음
        A8 같은 (행동 · 대상 · 인자, 판)을 이미 ALLOW 함
        → 걸린 것 없음: ALLOW
        → D 가 걸렸고 DC 의 기본 행동이 후보 안에 있고 실행기 행동(ActionSpec)임: SAFE_ACTION(그 행동)
        → 그 밖: DENY
        → 예외: DENY(rule E)
```

`rule` 은 판정을 정한 규칙이다. D 가 걸렸으면 D 이고, 아니면 A5 → A6 → A7 → A8 순서(MS 와 같은 순서)에서 처음 걸린 것이다. `reasons` 에는 걸린 규칙이 **모두** `[규칙] 까닭` 꼴로 들어간다.

ARBITRATE 는 짓지 않았다. 지금 후보는 하나뿐이고, BD-24 는 "옮길 규칙 없음" 이다.

## 2. 꼴

### 나가는 꼴 (닫힌 꼴 · 판본 · 정준 JSON · 내용 해시 — action 계약과 같은 방식, `action.canonical`)

| 꼴 | 판본 | 칸 |
|---|---|---|
| ValidationResult | `validation-result/1` | `validation_id`(`val-` + 해시) · `intent_id` · `ok` · `rule`(A0–A4 · E · `"0"`) · `reasons` |
| GuardResult | `guard-result/1` | `guard_id`(`grd-` + 해시) · `intent_id` · `verdict`(ALLOW · DENY · SAFE_ACTION) · `mode`(shadow · enforce) · `rule` · `state_refs` · `reasons` · **`safe_action`** |

꼴 안의 맞춤 검사:
- ALLOW ⇔ `rule == "0"` 이다.
- SAFE_ACTION ⇔ `safe_action` 이 있다.
- `state_refs` 는 `"<실체>@<판>"` · `"<실체>.<속성>"` 꼴이다. 정렬하고 겹침이 없다.

### 들어오는 꼴 (`guard/views.py`, 닫힌 꼴)

| 꼴 | 칸 | 채우는 쪽(예정) |
|---|---|---|
| DCView | `dc_id` · `offers{행동: [대상]}` · `seen{실체: 판}` · `decisions` · `handles` · `complete` · `stale_keys` · `default_decision` · `default_action` | MS 의 맥락 / DC 의 결정 문맥 |
| StateView | `entities{실체: {model, version, props{이름: {value, stale, age}}}}` · `allowed` | 배차 직전의 상태 저장소 읽기 |
| GuardModel | `specs`(ActionSpec: name · target_model · params · preconditions · risk) · `grants` · `risky` | Model(ActionSpec, BD-31) |

### ActionCommand 재료 (`guard/command.py`)

- ALLOW 이면 의도의 `action` · `target` · `args` 를 그대로 쓴다.
- SAFE_ACTION 이면 갈아 끼운 행동을 쓰고, `target=None` · `args={}` 로 둔다.
- DENY 에는 재료가 없다(예외를 낸다).
- `decision_ref` · `issued_at` · `deadline` 은 배차하는 쪽이 `build_command` 로 채운다.

## 3. baseline 표 · 지시와 다른 점 (판단 필요)

| # | 지시 · 표 | 여기 | 까닭 |
|---|---|---|---|
| G-D1 | GuardResult 에 `safe_action` 없음 | **더함** | SAFE_ACTION 이 무엇으로 갈아 끼웠는지 원장에 남아야 한다. 칸이 없으면 명령 재료를 다시 지을 수 없다 |
| G-D2 | `validate(intent, dc)` | `validate(intent, dc, model)` | A4 는 인자를 **Model 의 ActionSpec** 에 맞춘다(MS 도 registry 를 본다). 문맥에 실린 카드를 믿지 않는다 |
| G-D3 | `guard(intent, state_view, model)` | `guard(intent, dc, state, model)` | A5 는 결정이 **본 판**과 지금 판을 견준다. D 는 DC 의 완전성 · 기본 결정을 본다. 둘 다 DC 에 있다 |
| G-D4 | (MS 는 Arbiter 안에 기억) | A8 의 기억 = `StateView.allowed`, 호출자가 더함 | 순수 함수로 짓는다는 지시를 따랐다 |
| G-D5 | (MS 는 첫 규칙에서 멈춤) | 걸린 규칙을 모두 `reasons` 에 적음. `rule` 은 MS 순서의 첫 것 | DATA_FLOW §6.4 "논리곱 · 서로 풀어 주지 못한다". 판정과 rule 은 MS 와 같다(대조 시험) |
| G-D6 | — | 새 규칙 **D**(DATA_FLOW §6.5) | 끝난 기준 3. SAFE_ACTION 은 D 에서만 나온다(§4 A2) |
| G-D7 | MS: `none` → NOOP, `retrieve` → ALLOW R / A2 | 둘 다 **A0** | BD-97: 의도가 되지 않는다. 대조에서는 범위 밖으로 세었다 |
| G-D8 | MS: 의도에 `dc_id` 없음 | `intent.dc_id ≠ dc.dc_id` → A0 | 다른 문맥을 보고 낸 의도를 이 문맥의 근거로 통과시키지 않는다 |
| G-D9 | MS: 모르는 인자 타입은 통과 | 모르는 타입 → A4 | 닫는 쪽. MS 예시에는 그런 타입이 없어 대조에 나타나지 않는다 |
| G-D10 | — | 겨냥 없는 행동(`target=None`): 문맥이 대상 `None` 으로 내놓았을 때만 A2 · A3 를 지난다. 사전조건이 있으면 A6 | action 계약이 겨냥 없는 행동을 허용한다(STOP · ESCALATE). MS 에는 아직 없다 |

## 4. 가정 (assumption — baseline 확인 필요)

- **A1. "위험 등급"** 의 기본값은 `external` · `irreversible` 이다(`GuardModel.risky`). D 는 이 등급만 막고, `local` · `read` 는 DC 가 불완전해도 지난다. A7(허가가 필요한 등급)과 같은 경계다. Model 이 바꿀 수 있다.
- **A2. SAFE_ACTION 은 D 에서만** 낸다. 그리고 DC 가 고른 `default_action`(능력 있는 첫 후보)이 `default_decision` 안에 있을 때만 낸다. A5–A8 의 거부는 DENY 로 남긴다. 그래야 MS 처럼 다음 판에서 다시 제안하는 길이 그대로 남는다. 갈아 끼운 행동 자체는 A5–A8 로 다시 보지 않는다(목적 단위 행동이고 겨냥이 없다, DATA_FLOW §6.1 "안전 동작은 허용").
- **A3. 목적의 안전 기본 후보** 인 의도(예: ESCALATE)는 DC 가 불완전해도 D 가 막지 않는다(DATA_FLOW §6.1). A7 은 그대로 본다.
- **A4. shadow 의 뜻**: 판정은 모드와 무관하다. shadow 에서는 런타임이 자기 중재 결정대로 진행하고, GuardResult 는 기록 · 대조에만 쓴다.

## 5. 다음 (future — 이번에 하지 않음)

- **F1** ~~술어 언어와 인자 검사가 MS 와 같은 뜻으로 두 곳에 있다~~ → **CMD-G5 에서 닫음**: action 의 한 벌(`action.predicate` · `action.params`)을 쓴다(§10).
- **F2** BD-36: `confidence.kind=ordinal` 은 문턱으로 쓰지 못한다. StateView 에 `confidence` 칸이 아직 없다.
- **F3** GuardResult 에 규칙 판본(`guard-rules/1`)을 실을지.
- **F4** MS shadow 배선: MS 런타임이 Arbiter 옆에서 `evaluate` 를 부르고 GuardResult 를 DecisionRecord 에 싣는다. MS 파일이라 MS 세션의 일이다(CMD-M15 의 ActionIntent 다음).
- **F5** DC 의 결정 문맥(`complete` · `missing_required` · 유효성) → DCView 어댑터. DC 의 칸 이름과 맞춰야 한다.
- **F6** OQ-17 의 값이 정해지면 enforce 를 켜고, 안전 동작 여럿 가운데 고르는 규칙을 넣는다.
- **F7** `args_sig` · `deadline_ms`(BD-96 이 소비자가 생길 때로 미룬 것).

## 6. 시험

- 단위 시험: `tests/` 아래 꼴 · 입력 꼴 · 술어 · validate · guard · 명령 재료 · 경계(import · 의존 고정).
- 닫는 쪽으로만: 이미 ALLOW 가 아닌 경우에 제약 일곱 가지를 하나씩 더해도 ALLOW 가 되지 않음을 확인한다. 360 경우 × 7 = 2,520 번 판정한다.
- MS 대조(`eval/ms_contrast.py`, MS `8b9f292`): 경우 102,960 · 비교 68,688 · **같음 68,688 · 다름 0**. 범위 밖은 `none` 17,136 · `retrieve` 17,136 이다(BD-97).
  - 세계 변형: 맥락 예산 2 × 허가 3 × 맥락 뒤 변화 6(없음 · 판 오름 둘 · 120 초 낡음 · 30 초 · 상태 못 읽음). 제안은 두 바퀴 돌린다(A8).
  - MS 판정 규칙별 수: `0` 190 · A0 144 · A1 17,136 · A2 21,168 · A3 26,208 · A4 3,312 · A5 60 · A6 108 · A7 52 · A8 190 · E 120.
- 변이(`eval/mutation.py`): **58/58 RED**. ★ 표시 7 개(ALLOW 를 더하는 변이)가 모두 RED 다.
  - `--ms-only`(MS 대조만으로 돌림): 22/58 RED.
  - 대조가 못 잡는 36 개는 대부분 MS 에 없는 개념이다: D · SAFE_ACTION · 꼴 · `dc_id` · BD-97 · 명령 재료 · import 경계.
  - 나머지는 MS 예시 세계가 닿지 않는 길이다.
    - **A6 의 "사전조건이 지금 거짓"**: MS 는 사전조건이 맞는 도구만 맥락에 내놓는다. 그래서 값이 바뀌면 판이 올라 A5 가 먼저 걸린다.
    - **A8 열쇠의 rationale**: 대조 제안의 까닭 글이 하나뿐이다.
    - **없는 속성 · 걸린 속성**: 예시에 그런 사전조건이 없다.
  - 이 길들은 단위 시험이 잡는다.

## 7. DC 결정 문맥 → DCView (CMD-G2, `guard/dc_adapter.py`)

`dcview_from_dc(record, purpose, *, offers=None, seen=None) -> DCView`.
DC 코드는 import 하지 않는다. DC 가 내는 **데이터**만 읽는다.

| 입력 | 꼴 | 맞춰 보는 것 |
|---|---|---|
| `record` | DC `ctx.to_dict()` = `{digest, core, provenance}` | digest 를 다시 계산한다(DC `snapshot.digest_of` 와 같은 바이트열). 고친 기록은 거절한다 |
| 〃 | 또는 `core_dict()` = `{id, …core}` | 맞춰 볼 digest 가 없다. id 를 그대로 믿는다 |
| `purpose` | DC `Purpose` 의 `dataclasses.asdict` | 이름 · 판본이 core 와 같아야 한다(DC `spec_of` 와 같다). 모르는 칸은 거절한다 |
| `offers` · `seen` | 런타임이 넘긴다 | 겨냥 있는 행동과 결정이 본 실체의 판은 DC 에 없다(F4 에서 MS 가 넘긴다) |

| DCView 칸 | 어디서 |
|---|---|
| `dc_id` | `"dc-" + digest[:16]` |
| `complete` · `missing_required` | 필수 키(목적 refs 의 `required`, 기본값 참) 가운데 OBSERVED · DERIVED · INFERRED 가 아니고 NOT_APPLICABLE 도 아닌 것. DC `project.validity` 와 같은 식이다. 키 `역할[꼬리].이름` 은 역할로 맞춘다. 필수 키가 core 에 아예 없어도 빠진 것으로 센다(닫는 쪽) |
| `stale_keys` | core 상태 가운데 STALE 인 키 + 질의 행 속성 가운데 STALE 인 것 `"<질의>/<행>.<속성>"` |
| `default_decision` | 목적의 후보(순서 그대로) |
| `default_action` | core 의 값(DC 가 능력으로 고른 것). 후보 밖이면 거절한다 |
| `offers` | core 의 가능 행동 → `{행동: [None]}`(목적 단위 행동, 겨냥 없음) + 런타임의 `offers` |

맞지 않는 것은 모두 `ViewError` 다. 부르는 쪽(F4)은 그것을 DENY(E)로 다룬다.

### 지시와 다른 점 · 가정

- **G2-D1** 지시는 "core 에 `complete` · `missing_required` · `default_decision` 이 있다" 고 했다. **실제 DC core 에는 없다**.
  - `complete` · `missing_required` 는 core 의 유효성과 목적 명세의 필수 여부로 계산하는 **투영**이다(`dc/project.py`).
  - `default_decision` 은 목적 명세(`dc/purpose.py`)에 있다. core 에 있는 것은 `default_action` 뿐이다.
  - 그래서 어댑터는 목적 명세의 **데이터**를 함께 받는다. DC 의 MSStateReader 가 MS 에 넘기는 `record.complete` 를 받는 길도 있었다. 그러나 그것은 DC 가 계산한 결과를 믿는 것이고 고친 기록을 가를 수 없다. Guard 는 원 데이터에서 다시 계산한다.
- **G2-D2** `core_dict()` 만 받으면 변조를 가를 수 없다. digest 가 core + provenance 의 해시라서다. 받기는 하되 문서에 적는다. F4 에서는 `to_dict()` 를 넘기기를 권한다.
- **G2-D3** `DCView.missing_required` 칸을 더했다. 까닭 글에만 쓰고, 판정은 `complete` 로 한다. 입력 꼴이고 동결된 계약(`guard-result/1`)은 바뀌지 않았다.
- `stale_keys` 에는 STALE 을 모두 싣는다. D 가 그 가운데 무엇을 보는지는 §8(BD-103)이 정한다.

### 시험

- `eval/dc_fixtures.py` 가 DC 의 **실제 빌더**(통합 머리 `ce3a0bc`)로 여덟 문맥을 지어 `tests/fixtures/dc_contexts.json` 에 둔다.
  - 여덟 문맥: 완전 · 불완전(기본 ESCALATE / STOP) · 필수 아닌 키 낡음 · 필수 키 낡음 · 기본 결정 없음 · 질의 행 속성 낡음.
  - 사례마다 DC 가 **스스로** 계산한 투영(`ctx.validity` · STALE · `default_action`)을 정답으로 함께 저장한다.
- `tests/test_dc_adapter.py`:
  - 어댑터 출력이 DC 투영과 같다(8/8). `core_dict` 로 넣어도 같은 DCView 가 나온다.
  - 고친 기록 · 목적 판본 다름 · 꼴 다름은 거절한다.
  - D 가 그 위에서 선다:
    - 위험 행동 reboot: 완전 → ALLOW · 불완전 → SAFE_ACTION(DC 의 기본 행동) · 기본 없음 → DENY · 낡은 키는 §8
    - local 행동은 어디서나 ALLOW 다. 안전 기본 후보(ESCALATE)는 막지 않는다.
  - DC 가 옆에 있으면 고정 파일이 지금 DC 가 짓는 것과 같은지 본다(드리프트).
- 변이(`eval/mutation.py`): G1 의 58 개 + 어댑터 13 개 = **71/71 RED**.

## 8. D 의 낡은 키 범위 (CMD-G3, BD-103)

D 가 보는 낡은 키 = `stale_keys` ∩ (필수 키 ∪ 의도의 `used_keys`) 다(`rules.stale_in_scope`).
- `used_keys` 의 `query:<이름>` 은 그 질의의 행 속성 전부(`"<이름>/<행>.<속성>"`)다. 이름은 통째로 맞춘다(`query:ho` 는 `hot/…` 이 아니다).
- 필수 키는 `DCView.required_keys` 다. 어댑터가 목적 refs 의 `required` 로 채우고, DC 자신의 `StateView.required` 와 같음을 시험이 본다.
  - DC 문맥에서 필수 키가 STALE 이면 이미 `complete=False` 다. 그래도 D 는 두 길을 따로 본다. 손으로 지은 문맥(complete=True, 필수 키 STALE)도 막기 위해서다.
- 까닭: 결정이 쓰지도 않고 필수도 아닌 키가 낡은 것은 그 행동의 근거가 아니다. 문맥 전체를 보면 완전한 문맥에서도 위험 행동이 SAFE_ACTION 으로 바뀌었다(G2 표의 `exec_stale_optional` · `cr_query_stale`).
- `allow_stale` 로 일부러 보인 값이라도 의도가 썼으면 D 를 건다(엄한 쪽).

판정표 — 위험 행동 `reboot`, DC 실제 빌더 문맥:

| 문맥 | 의도의 used_keys | Guard |
|---|---|---|
| exec_complete | — | ALLOW |
| exec_incomplete_escalate · _stop | — | SAFE_ACTION → ESCALATE · STOP (불완전) |
| exec_stale_optional (`tool[Bash].tool_execution_health` 낡음, 필수 아님) | — | **ALLOW** (G2: SAFE_ACTION) |
| 〃 | `tool[Bash].tool_execution_health` | SAFE_ACTION → ESCALATE |
| exec_stale_required (`runtime.rate_limit_state` 낡음, 필수) | — | SAFE_ACTION → ESCALATE (불완전 · 필수 키 낡음) |
| exec_no_default | — | DENY (D) |
| cr_complete | — | ALLOW |
| cr_query_stale (`hot/srv07.fan_rpm` 낡음) | — · `query:cold` · `session.context_pressure` | **ALLOW** (G2: SAFE_ACTION) |
| 〃 | `query:hot` 또는 `hot/srv07.fan_rpm` | SAFE_ACTION → KEEP |

시험(G3): 단위 80 · 변이 **77/77 RED**(G2 의 71 + 범위 변이 6) · MS 대조 68,688 비교 다름 0(그대로).

## 9. SAFE_ACTION 은 실행기 행동으로만 (CMD-G4, BD-104)

- D 가 갈아 끼울 `default_action` 이 GuardModel 의 ActionSpec 에 없으면 **DENY(D)** 를 낸다.
  - 까닭 글: "안전 기본 X 은 실행기 행동이 아니다(ActionSpec 없음) -- 갈아 끼우지 않는다".
- 발견한 곳: MS shadow 배선(MS `bb90625`).
  - MS 가 읽는 목적 `context_runtime` 의 기본 결정은 `KEEP` 이다.
  - KEEP 은 CR 안의 맥락 결정이고, 실행기 행동이 아니다(BD-100).
  - 그대로 두면 enforce 에서 도구 의도가 실행기 밖 행동으로 바뀐다.
- 규칙 순서(D 가 A7 보다 앞섬)는 그대로다. 허가 없는 reboot 도 이 문맥에서는 DENY(D) 다.

| 문맥 | 의도의 used_keys | G3 | **G4** |
|---|---|---|---|
| cr_query_stale (기본 KEEP) | `query:hot` · `hot/srv07.fan_rpm` | SAFE_ACTION → KEEP | **DENY (D)** |
| exec_* (기본 ESCALATE · STOP, ActionSpec 있음) | — | SAFE_ACTION | SAFE_ACTION (그대로) |

시험(G4): 단위 81 · 변이 **78/78 RED**(★ 실행기 밖 행동으로 갈아 끼움 포함) · MS 대조 68,688 비교 다름 0(그대로).

## 10. action 한 벌로 옮김 (CMD-G5, BD-108 · BD-109)

- action 의존을 `3995fdb3ba487f31d841d3e11b710e64f0d523db` 로 다시 고정했다(`pyproject.toml`). 설치본의 `direct_url.json` `commit_id` 로 확인했다.
- 술어 · 인자 검사:
  - `guard/rules.py` · `guard/views.py` 가 `action.predicate` · `action.params.check_args` 를 바로 import 한다.
  - guard 안의 자기 구현은 지웠다. 경계 시험 `OneLanguage` 가 붙든다: 모듈 최상위의 `holds` · `check` · `props_of` · `check_args` · `OPS` 가 없다.
  - **옮김 흔적**: `guard/predicate.py` · `guard/params.py` 는 action 을 다시 내보내기만 하는 두 줄 모듈로 남겼다.
    - 까닭: action 의 대조 시험(`SameAsGuard` · `Params.test_same_as_guard`)이 옆 저장소의 `guard.predicate` · `guard.params` 를 import 한다.
    - 지우면 guard 를 옆에 둔 action 시험이 ERROR 3 이 된다. 쟀다: 지운 상태에서 `GUARD_REPO=../guard` 로 돌리면 ERROR 3.
    - 경계 시험이 두 모듈에 import 말고 아무것도 없음을 붙든다. action 이 그 시험을 걷으면 지운다.
- 행동 명세: `GuardModel.from_action_model(ActionModel, grants=(), risky=DEFAULT_RISKY)`.
  - 명세는 `action.spec.to_guard_spec` 의 투영이다(이름 · 대상 모형 · 인자 · 사전조건 · 위험).
  - 사후조건 · 창 · 판본 · 설명은 Guard 로 오지 않는다.
  - 허가 · 막는 위험 등급은 운영자 설정으로 남는다. OQ-17 의 안전 동작 순서는 아직 넣지 않았다(E3 enforce 때).
  - 위험 등급 목록(`RISKS`)도 action 의 것을 쓴다.
- 기존 공개 API(`ActionSpec(name, target_model, params, preconditions, risk)` · `GuardModel(specs, grants)` 등)는 그대로다. MS `ms/guard_shadow.py` 가 그대로 쓴다.
- MS 대조: GuardModel 을 **ActionModel 길**(MS 도구 정의 → `ActionSpec.from_tool` → `ActionModel` → `from_action_model`)로 짓는다. ToolRegistry 에서 바로 지은 것과 행동 명세가 같은지도 센다(`retrieve` 만 빼고, 모델 다름 0).
