# Technical Requirements Document (TRD) - 기술 설계안

> **작성 시점**: Day 5
> **상태**: 구현 전 기술 설계 완료 (Technical Design)
> **시스템의 뼈대와 데이터의 흐름을 정의한다.**

---

## 1. 시스템 아키텍처 (Architecture)

### 1.1 기술 스택
- **Application**: Streamlit
- **AI/CV Engine**: MediaPipe Pose (BlazePose), OpenCV
- **Computation**: NumPy (Vectorized angle calculation)

### 1.2 모듈 구조 (로컬 실행 기준)
```text
[Local Webcam] <-> [Streamlit App (Main)]
                     |
                     +-- [Pose Analyzer] (MediaPipe)
                     |
                     +-- [Rule Engine] (Geometry logic)
                     |
                     +-- [Feedback UI] (Real-time overlay)
```

---

## 2. 데이터 흐름 (Data Flow)

### 2.1 실시간 처리 루프 (Local Mode)
1. **Capture**: `cv2.VideoCapture(0)`를 통한 로컬 웹캠 프레임 획득.
2. **Transform**: 이미지를 RGB로 변환 및 MediaPipe 입력 규격에 맞게 리사이징.
3. **Extraction**: `pose.process()`를 호출하여 랜드마크 좌표(x, y, z) 획득.
4. **Calculations**: 
   - 무릎 각도: `hip`, `knee`, `ankle` 좌표 간 벡터 내적 활용.
   - 상체 기울기: `shoulder`, `hip` 좌표 간 수직 각도 계산.
5. **Logic**: 계산된 수치를 Threshold와 비교하여 피드백 상태 결정.
6. **Rendering**: 영상 위에 스켈레톤, 각도, 메시지를 `cv2.putText` 등으로 합성 후 Streamlit에 표시.

---

## 3. 핵심 알고리즘 (Core Logic)

### 3.1 벡터 기반 각도 계산
- 세 점 A, B, C에 대하여 벡터 BA와 BC 사이의 각도 $\theta$ 계산:
  $$\cos\theta = \frac{\vec{BA} \cdot \vec{BC}}{|\vec{BA}| |\vec{BC}|}$$
  $$\theta = \arccos(\cos\theta)$$
- 특징: 2D 평면이 아닌 3D 좌표를 활용하여 깊이 정보를 일부 반영함.

### 3.2 상태 기반 판정 로직 (국면별 판단)
- **Down Phase**: 무릎 각도가 줄어드는 구간. 자세가 충분히 깊은지 판단.
- **Up Phase**: 다시 올라오는 구간. 상체 기울기가 과도하지 않은지 확인하여 피드백 제공.
- **오탐 방지 및 안정화 (Robustness)**:
  - 단순 국면 토글/깜빡임을 방지하기 위한 **스무딩(Smoothing)** 및 **히스테리시스(Hysteresis)** 로직 적용.
  - 신뢰도(Confidence)가 낮거나 인식 실패 시 피드백을 보류(Pending)하는 규칙 적용.
  - (세부 임계값, 로직 흐름, 보류 조건 등은 `decision_spec.md` 문서를 참조한다.)

---

## 4. 인프라 및 보안 (Infrastructure & Security)

### 4.1 배포 및 환경 제약
- **Local Environment**: 본 MVP는 로컬 실행을 기본으로 하며, 직접적인 카메라 하드웨어 접근을 위해 OpenCV를 사용함.
- **Cloud Warning**: Streamlit Cloud 등 원격 환경 배포 시, 서버 기반인 `cv2.VideoCapture`는 사용자 브라우저 카메라에 접근할 수 없음. 이 경우 `streamlit-webrtc`를 통한 클라이언트 사이드 프레임 전송 구현이 필수적임.

### 4.2 보안 및 프라이버시
- **No Data Storage**: 어떠한 이미지나 좌표 데이터도 서버나 외부 DB에 영구 저장하지 않음.
- **Local Processing**: 로컬 실행 시 모든 영상 데이터는 사용자 PC의 메모리 내에서만 처리되고 즉시 파기됨.
- **Cloud Privacy**: 클라우드 배포 시에는 영상 프레임이 서버로 전송되는 방식에 따른 별도의 개인정보 보호 안내가 필요함.

---

## 변경 이력
- **v1 (2026-05-13)**: 로컬 중심 아키텍처 정의 및 클라우드 배포 제약 사항 추가
- **v1.1 (2026-05-18)**: 오탐 방지 로직(스무딩, 신뢰도 보류 등) 도입 및 decision_spec.md 참조 추가

---
**작성자**: FitCheck AI Team
**최종 갱신**: 2026-05-18
