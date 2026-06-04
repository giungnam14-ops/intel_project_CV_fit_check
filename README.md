# Batch Analysis Usage

- **Button**: 📂 전체 테스트 영상 일괄 분석
- **Location**: Below the single video selection UI.
- **Function**: Analyzes all videos in `test_videos` folder sequentially.
- **Progress**: Displays a progress bar and status text.
- **Result**: Shows a summary table with columns:
  - filename
  - auto_result
  - skeleton_detection_rate
  - squat_count
  - count_confidence
  - knee_angle_min
  - torso_angle_max
  - feedback_type
  - feedback_message
- **CSV**: Results are saved to `results/eval_result_v1.csv` (overwrites existing rows by filename).

> **웹캠 하나로 정석 자세를 찾아주는 당신만의 AI 홈트 자세 코치**

---

> [!IMPORTANT]
> **현재 프로젝트 상태: 영상 업로드 기반 MVP 구현 완료 + 실시간 웹캠 분석 1차 확인 단계**
> 본 프로젝트는 설계 문서 및 프로토타입을 바탕으로 **1차 영상 업로드 기반 스쿼트 자세 분석 MVP v1** 구현을 완료했으며, 현재 **실시간 웹캠 기반 자세 코칭 프로토타입**의 1차 기능 검증 단계에 있습니다.
> - **완료된 주요 기능**: MediaPipe 기반 관절 인식, 무릎 각도/상체 기울기 5프레임 스무딩 연산, 피드백 유형 분류(GOOD, NOT_DEEP, LEAN_FORWARD, LOW_VISIBILITY), 스쿼트 횟수 카운팅 및 카운팅 신뢰도 표시, 사용자 친화적인 결과 리포트 UI 적용, CSV 누적 저장.
> - `mockup/` 폴더: 클릭 가능한 대화형 UI 프로토타입을 확인하실 수 있습니다.
> - `app/` 폴더: 영상 파일 업로드 자세 분석 코드(`main.py`)가 구동됩니다.
> - **온디맨드(On-Demand) AI 로드**: 사용자가 영상을 선택하고 [분석 시작] 버튼을 누른 즉시 메모리에 MediaPipe Pose를 로드하여 불필요한 시작 오류를 방지합니다.
> - **향후 개선 계획**: 실제 카메라 연동을 통한 실시간 전신 웹캠 코칭 기능은 다음 고도화 단계에서 진행할 예정입니다.
> - **주의 사항**: Windows 환경에서 한글 경로로 인한 MediaPipe 모델 유실 에러를 방지하려면 반드시 프로젝트 폴더를 영문 경로(예: `C:\FitCheck-AI`)에 두어야 합니다.

---

## 1. 환경 요구사항 (System Requirements)
- **권장 Python 버전**: **Python 3.10 또는 3.11 64-bit**
  *(주의: Python 3.12+ 이상 환경에서는 C++ 컴파일 휠 충돌로 인해 고정 버전 설치 과정에서 실패할 수 있습니다.)*
- **의존성 안정성**: MediaPipe solutions API 참조에 관한 모듈 안정성과 누락 에러 방지를 위해 아래 버전들이 고정되어 설치됩니다.
  - `mediapipe==0.10.9` (초안정 하향 평준화 고정 버전)
  - `numpy` 

---

## 2. 개요 (Overview)
**FitCheck AI**는 "내 자세가 맞나?" 고민하는 홈트 입문자를 위한 실시간 자세 코칭 서비스입니다. 별도의 장비 없이 카메라만으로 사용자의 관절을 추적하고, 초보자가 이해하기 쉬운 자세 피드백을 즉시 제공하여 안정적이고 효과적인 운동을 돕습니다.

---

## 3. UI 프로토타입 확인 방법 (Mockup)
본격적인 AI 기능 연동 전, 전체 사용자 경험 흐름을 검증할 수 있는 정적/대화형 UI 목업을 제공합니다. (실제 카메라 연동 및 AI 자세 측정은 작동하지 않는 프론트엔드 시안입니다.)

### 확인 방법
1. 웹 브라우저에서 [mockup/index.html](file:///c:/Users/User/Desktop/%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8_2%EB%B2%88/FitCheck-AI/mockup/index.html) 파일을 직접 엽니다. (윈도우 탐색기에서 파일 더블클릭)
2. 스마트폰 모형 내부의 버튼들을 클릭하면 다음 단계 화면으로 부드럽게 슬라이드 전환됩니다.
3. 화면 왼쪽의 '진행 순서 가이드' 탭을 직접 클릭하여 원하는 단계로 바로 이동하여 테스트할 수도 있습니다.

---

## 4. 분석 MVP v1 실행 방법 (Application)
Day 5 Build v1에서는 MediaPipe와 OpenCV 알고리즘의 안전성 검증을 위해 **두 가지 영상 입력 방식**을 제공합니다.

### ⚙️ 영상 입력 방식 및 온디맨드(On-Demand) 로딩 방식
- **1) test_videos 폴더에서 선택**: 프로젝트 루트의 `test_videos/` 폴더에 영상(.mp4, .mov, .avi)을 넣어두면 앱에서 자동으로 목록을 불러와 손쉽게 선택하고 테스트할 수 있습니다. 
  *(주의: 영상 테스트 시 원본 영상이 외부로 공유되지 않도록 로컬 환경 내에서만 안전하게 관리해 주세요.)*
- **2) 직접 파일 업로드**: 기존 방식대로 원하는 영상을 앱 화면에서 직접 업로드하여 분석할 수도 있습니다.
- **온디맨드 로딩**: 사용자가 어플리케이션에 접속하는 시점에는 AI 엔진을 로드하지 않으며, 영상을 선택/업로드하고 **[분석 시작] 버튼을 누른 즉시** MediaPipe 엔진 초기화를 시도합니다.
- **결과 자동 저장 (CSV)**: 테스트 영상 분석이 완료되면 결과 요약 데이터(평균 각도, 스켈레톤 인식 비율, 자동 판정 등)가 프로젝트 내 `results/eval_result_v1.csv` 파일에 누적되어 자동 기록됩니다. (단순 수치 기반 요약만 저장되며 원본 영상 데이터는 저장되지 않습니다. / 최근 업데이트: CSV 스키마 정리 및 smoothing_applied 컬럼 추가 완료, CSV 저장 로직 수정: 축약 문자열 저장 방지 및 utf-8-sig 저장)

### 🚀 쉬운 실행 방법 (Windows 권장)
1. 윈도우 파일 탐색기에서 프로젝트 루트 폴더에 위치한 **`run_app.bat`** 파일을 **마우스 더블클릭**하여 실행합니다.
   *(한글 깨짐 및 실행 에러 방지를 위해 배치파일 내부 메시지는 영어로 작성되어 있습니다.)*
2. 전역 Streamlit과의 오버레이 간섭을 완전히 원천 차단하기 위해, 자동으로 프로젝트 가상환경 내에 있는 **`.venv\Scripts\python.exe -m streamlit run app\main.py`** 명령어를 호출하여 안전하게 구동됩니다.
3. PowerShell 사용자는 콘솔에서 아래 스크립트를 입력해 간단하게 구동할 수도 있습니다.
   ```powershell
   .\run_app.ps1
   ```

### 🎬 실시간 웹캠 분석 v1 (로컬 OpenCV 기반 프로토타입)

**현재 상태**: 로컬 PC 웹캠을 이용한 실시간 자세 분석의 프로토타입 구현입니다.

#### 기능 명세
- **입력 방식**: OpenCV `cv2.VideoCapture(0)` - 로컬 PC의 웹캠만 지원
- **실시간 표시**: 웹캠 프레임, MediaPipe 스켈레톤 오버레이, 무릎 각도, 상체 기울기, 피드백
- **스무딩**: 최근 5프레임 이동평균 적용
- **피드백**: 기존 `feedback.py`의 규칙 재사용 (GOOD, NOT_DEEP, LEAN_FORWARD, LOW_VISIBILITY)
- **미포함 기능**: CSV 저장, 스쿼트 카운팅 (향후 고도화)
- **클라우드 배포**: WebRTC는 현재 미구현 (향후 고도화 예정)

#### 실행 방법
콘솔에서 다음 명령어를 입력하세요:
```bash
streamlit run app/webcam_app.py
```

#### UI 흐름
1. **"🎬 웹캠 시작"** 버튼을 클릭하면 로컬 웹캠이 활성화됩니다.
2. 실시간 프레임에 MediaPipe 스켈레톤이 오버레이됩니다.
3. 화면에 다음 정보가 표시됩니다:
   - 무릎 각도 (Knee Angle)
   - 상체 기울기 (Torso Lean)
   - 인식 상태 (✓ 인식 / ✗ 대기)
   - 실시간 코칭 피드백
4. **"⏹️ 웹캠 중지"** 버튼을 클릭하면 웹캠이 종료됩니다.

#### 주의사항
- 웹캠 연결 상태를 확인한 후 실행하세요.
- 충분한 조명과 카메라 앵글을 확인하세요 (측면에서 전신이 보이도록).
- 저사양 PC에서는 프레임 손실이 발생할 수 있습니다.

---

## 5. 문제 해결 (Troubleshooting)

### 🚨 [필독] MediaPipe 한글 경로 오류 해결 방법 (윈도우 환경 버그)
* **오류 증상**: 영상을 업로드한 뒤 [분석 시작] 버튼을 누를 때 `Failed to initialize MediaPipe Pose` 또는 `.binarypb` 모델 파일이 유실되었다는 에러 발생.
* **원인**: 본 프로젝트가 위치한 절대경로에 **한글 폴더명(예: `프로젝트_2번`)이 포함되어 있을 경우**, MediaPipe 내부 C++ 리소스 로더가 CP949와 UTF-8 사이의 인코딩을 올바르게 파싱하지 못하여 물리적으로 존재하는 모델 파일(`pose_landmark_cpu.binarypb`)을 찾지 못하고 에러를 내뱉게 됩니다.
* **권장 실행 절대경로**:
  - **`C:\Users\User\Desktop\project_2\FitCheck-AI`**
  - **`C:\FitCheck-AI`**
  - *(주의: 상위 경로 상에 한글이나 특수문자가 단 하나도 포함되지 않은 순수 영문/숫자(ASCII) 경로에 프로젝트를 두어야 합니다.)*
* **해결 방법 및 결과**: 프로젝트 폴더를 영문 경로로 변경한 뒤 `.venv`를 삭제하고 재설치하여 해결. MediaPipe Pose 모델이 정상 초기화되고, 영상 업로드 기반 자세 코칭 및 자세 안정성 인식이 정상 동작함을 확인했습니다.

#### 🛠️ 오류 해결을 위한 순서 가이드 (Checklist)
1. 현재 실행 중인 모든 CMD 콘솔 창, Streamlit 로컬 서버 프로세스, 그리고 웹 브라우저 탭을 완전히 **종료**해 주세요.
2. 현재의 `FitCheck-AI` 폴더를 영문 경로(예: `C:\Users\User\Desktop\project_2\FitCheck-AI`)로 이동시킵니다.
3. 새로 복사한 영문 폴더 안으로 들어가서, 기존에 설치된 가상환경 폴더인 **`.venv` 폴더를 통째로 삭제**해 주세요.
4. **`run_app.bat`** 파일을 마우스 **더블클릭**하여 실행합니다.
   - 자동으로 깨끗한 새 가상환경 생성, 필수 라이브러리 설치, 진단이 순서대로 가동됩니다.
5. 로컬 서버 브라우저 창이 정상 로드되면 스쿼트 자세 영상을 업로드하고 **`[분석 시작]`** 버튼을 눌러 스켈레톤 인식을 최종 테스트합니다.

#### 🔍 환경 상태 및 재설치 정밀 도구 활용
- **`scripts/check_env.bat`**: 가상환경의 파이썬 구도 및 `pose_landmark_cpu.binarypb` 파일의 물리적 존재 유무를 확인해 `logs/check_env_log.txt`에 기록합니다.
- **`scripts/rebuild_env.bat`**: 가상환경을 처음부터 다시 깔끔하게 세척하여 0.10.9 버전으로 완벽히 재구축하고 `logs/rebuild_env_log.txt`에 기록합니다.

---

## 6. 분석 화면 핵심 피드백 (coaching criteria)
- **무릎 각도**: Hip-Knee-Ankle 2D 각도가 $110^\circ$를 초과할 때 피드백을 제안합니다. (`"조금 더 깊이 앉아볼까요?"`)
- **상체 기울기**: 수직 가상선 대비 상체 굽힘도가 $45^\circ$를 초과할 때 피드백을 제안합니다. (`"허리를 조금 더 곧게 펴볼까요?"`)
- **안정선 도달**: 두 기준을 모두 충족하면 안정화 메시지를 띄웁니다. (`"안정적인 자세예요! 계속 진행해보세요."`)
- **데이터 스무딩**: 최근 5프레임 이동평균 스무딩을 적용하여 관절 인식 값의 튐 현상을 줄이고 안정적인 자세 판정을 제공합니다.

---

## 7. 프로젝트 구조 (Structure)
- `docs/`: 기획 및 의사결정 명세 문서 (`prototype_plan.md`, `ui_mockup_guide.md`, `project_summary.md` 등)
- `architecture/`: 데이터 흐름도 및 시퀀스 다이어그램 명세
- `mockup/`: 클릭 가능한 HTML/CSS/JS 기반 UI 프로토타입 시안
- `app/`: Day 5 Build v1 스쿼트 영상 업로드 기반 자세 분석 MVP 소스 코드
  - `requirements.txt`: Streamlit, OpenCV, MediaPipe 등 설치 의존성 파일
  - `main.py`: 분석 프리뷰 렌더링 및 대시보드 리포트 Streamlit 인터페이스
  - `pose_utils.py`: MediaPipe Pose 초기화 및 관절 각도/상체 슬로프 벡터 계산 라이브러리
  - `feedback.py`: 각도별 코칭 룰 엔진 규칙
- `scripts/`: 개발 및 검증 도구 폴더
  - `check_env.py`: 가상환경 전반 및 모델 파일 누락 확인 자가 진단 도구
  - `check_env.bat`: 자가 진단 도구 자동 수행 스크립트 (English-only)
  - `rebuild_env.bat`: 가상환경 초기 세척 및 0.10.9 완전 재조립 도구 (English-only)
  - `reinstall_mediapipe.bat`: MediaPipe 패키지만 강제 100% 클린 재설치 수행하는 스크립트 (English-only)
- `logs/`: 설치 상태 및 파이프라인 진단 기록용 폴더
  - `check_env_log.txt`: check_env 실행 진단 기록 로그
  - `rebuild_env_log.txt`: rebuild_env 재구성 기록 로그
  - `reinstall_mediapipe_log.txt`: MediaPipe 강제 복구 기록 로그
- `run_app.bat`: 윈도우 원클릭 자동 환경구성 및 구동 배치 스크립트 (English-only)
- `run_app.ps1`: 파워쉘 전용 자동 세팅 및 구동 스크립트
- `README.md`: 프로젝트 안내 및 종합 가이드

---

## 8. 원칙 (Principles)
- **No Paid API**: 유료 API 없이 오픈소스 로직만으로 100% 무료 동작하도록 설계.
- **Privacy Policy (설계 원칙)**: 
  - MVP 설계 기준상, 외부 데이터베이스나 클라우드로 영상을 전송하거나 수집하지 않는 것을 원칙으로 합니다.
  - 영상 처리 및 랜드마크 추출 알고리즘은 100% 로컬 환경의 프라이버시 존 내에서 작동합니다.

---
**프로젝트 최종 요약**
FitCheck AI는 영상 업로드 기반으로 스쿼트 자세를 분석하고, 초보자가 이해하기 쉬운 자세 코칭 피드백과 운동 흐름 정보를 제공하는 컴퓨터비전 기반 MVP입니다.

**최종 갱신**: 2026-05-21
