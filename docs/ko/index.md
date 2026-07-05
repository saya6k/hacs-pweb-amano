# PWEB Amano — Home Assistant 통합구성요소

**PWEB**(아마노코리아 관리사무소 시스템) 아파트/오피스텔 관리 포털용 Home Assistant 커스텀 통합구성요소입니다 — `https://a12345.pweb.kr` 같은 사이트가 대상입니다. 공개 API가 없어 아이디/비밀번호로 직접 로그인 후 HTML을 파싱합니다.

## 현재 상태

할인(discount) 화면은 구현되어 있습니다: 잔여 할인 잔액, 등록 내역, 현재 주차된 차량에 대한 즉시 실행 서비스. 일반 대시보드 데이터(공지, 관리비 등)는 아직 범위 밖입니다 — 해당 페이지 구조를 아직 확인하지 못했습니다.

5분마다 갱신되는 엔티티:

- **Last sync** — 마지막으로 로그인/조회에 성공한 시각.
- **Discount balance** — 잔여 할인 잔액(원).
- **Discount registration status** — 사이트에 등록된 전체 할인 종류 목록을 `available_discount_types` 속성으로 함께 제공.
- **Refresh** 버튼 — 즉시 갱신을 실행.

설정(또는 설정 → 기기 및 서비스 → PWEB Amano → Configure)에서 특정 차량 번호판을 추적 대상으로 지정하면, 번호판별로 별도 기기가 생성되고 다음이 추가됩니다:

- **Parking history** 캘린더 — 각 방문의 실제 입차~출차 구간을 표시.
- **Vehicle entry/exit** 이벤트 — "entry"는 해당 번호판의 등록 내역이 처음 확인될 때, "exit"는 차량이 출차 처리되는 시점에 실시간으로 발생.

즉시 실행 가능한 서비스 2가지도 제공됩니다:

- **`pweb_amano.register_discount`** — 현재 주차된 차량(번호판 기준, 추적 중인 내 차량으로 한정되지 않음)에 할인을 등록.
- **`pweb_amano.list_unregistered_vehicles`** — 현재 주차되어 있지만 아직 할인이 등록되지 않은 차량 목록을 조회.

## 설치 (HACS)

1. HACS → Integrations → ⋮ → Custom repositories → 이 저장소를 "Integration"으로 추가.
2. **PWEB Amano** 설치 후 Home Assistant 재시작.
3. 설정 → 기기 및 서비스 → 통합구성요소 추가 → **PWEB Amano**.
4. 포털 주소의 숫자 lot-area 코드(예: `a12345.pweb.kr`라면 `12345`)를 입력하고, 감지된 사이트 이름을 확인한 뒤 아이디와 비밀번호를 입력.
5. 필요하면 추적할 차량 번호판을 바로 입력 — 나중에 Configure에서 추가/수정 가능.

## 보안

비밀번호는 포털 자체 로그인 페이지와 동일한 방식으로 클라이언트 측에서 SHA-256으로 해시된 뒤 전송됩니다. 평문으로 로그에 남거나 config entry 이외의 곳에 저장되지 않습니다.
