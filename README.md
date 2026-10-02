# guard

VALIDATE · ARBITRATE · GUARD 의 저장소다. 자리는 L4 와 L5 사이다(baseline BD-07 · BD-20 · BD-24, `BASELINE.md` §10.1).
지금은 **shadow 의 뼈대만** 있다(baseline#7 CMD-G1).

```
Policy(MS) ─ActionIntent─► validate (A0–A4) ─► [arbitrate: 후보 하나 — 옮길 규칙 없음] ─► guard (D · A5–A8) ─► ActionCommand 재료
                              결정이 본 것(DCView)                                       지금 상태(StateView) · 규칙(GuardModel)
```

- **닫는 쪽으로만** 간다. VALIDATE 가 막은 의도는 GUARD 로 가지 않는다. 걸린 규칙이 하나라도 있으면 ALLOW 가 아니다. 예외가 나면 DENY 다.
- **순수 함수**다. 같은 입력이면 같은 결과가 나온다. 되풀이(A8)의 기억은 호출자가 `StateView.allowed` 로 넘긴다.
- **shadow 만** 켠다. enforce 는 OQ-17(안전 동작 전순서의 값)이 정해진 뒤에 켠다. 지금 `mode="enforce"` 를 넘기면 거절한다.
- Policy · CR · MS · DC 를 import 하지 않는다. 의존은 action 계약(`action-contract/1`, 커밋 `443f8eb` 고정)과 표준 라이브러리뿐이다.

설계 · baseline 표와 다른 점 · 가정은 [`docs/GUARD.md`](docs/GUARD.md) 에 있다.

```
pip install -e .                                  # action 계약을 고정 커밋으로 받는다
python3 -m unittest discover -s tests -t .        # 시험. MS 가 옆 디렉터리(또는 MS_REPO)에 있으면 MS arbiter.py 와 대조한다
python3 eval/ms_contrast.py                       # 대조만 따로 돌린다. 다른 판정이 있으면 표로 찍는다
python3 eval/mutation.py                          # 변이 시험. 모두 RED 여야 한다(MS 가 있어야 돈다)
```

설치하지 않았으면 action 저장소가 옆 디렉터리(또는 `ACTION_REPO`)에 있어야 시험이 돈다.

통로: baseline 이슈 [#7](https://github.com/cogito5170/baseline/issues/7). 소유: Guard 세션.
