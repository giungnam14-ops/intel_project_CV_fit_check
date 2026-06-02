# 시퀀스 다이어그램 (Sequence)

> **작성 시점**: Day 11
> **사용자 인터랙션에 따른 시스템 내부의 동작 순서를 정의한다.**

---

```mermaid
sequenceDiagram
    participant User as 사용자
    participant App as Streamlit UI
    participant MP as MediaPipe Pose
    participant Engine as 분석 엔진
    
    User->>App: 카메라 권한 허용 및 운동 시작
    loop 매 프레임마다 반복
        App->>MP: 비디오 프레임 전달
        MP->>MP: 관절 랜드마크 추출
        MP-->>App: 좌표 데이터(x, y, z) 반환
        App->>Engine: 관절 좌표 전달
        Engine->>Engine: 각도 계산 및 자세 판정
        Engine-->>App: 코칭 메시지 및 점수 전달
        App-->>User: 스켈레톤 가이드 + 메시지 + 점수 표시
    end
    User->>App: 운동 종료 요청
    App->>Engine: 전체 데이터 요약 요청
    Engine-->>App: 최종 리포트 데이터 생성
    App-->>User: 결과 대시보드 출력
```

---

## 주요 단계
1. **초기화**: 사용자가 웹캠 접근을 허용하면 MediaPipe 모델이 로드됩니다.
2. **실시간 루프**: 프레임 단위로 '추출 -> 계산 -> 피드백' 프로세스가 지연 없이 수행됩니다.
3. **세션 종료**: 운동이 끝나면 누적된 데이터를 바탕으로 종합적인 피드백 리포트를 생성합니다.

---
**작성자**: FitCheck AI Team
**최종 갱신**: 2026-05-13
