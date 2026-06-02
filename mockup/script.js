// =================================================================
// FitCheck AI - 대화형 UI 프로토타입 스크립트
// =================================================================
// 이 스크립트는 실제 서버 연결이나 카메라 없이, 프론트엔드 단에서
// 버튼 클릭 시 각 화면을 부드럽게 전환(슬라이드)해 주는 역할을 합니다.

document.addEventListener('DOMContentLoaded', () => {
    // 4개 화면을 담은 슬라이더 엘리먼트
    const slider = document.getElementById('screen-slider');
    
    // 왼쪽 데스크톱 패널의 진행 상황 단계 가이드 아이템들
    const steps = document.querySelectorAll('.flow-steps .step');

    // 스마트폰 내부 각 화면의 트랜지션 버튼 요소들 선택
    const btnStart = document.getElementById('btn-start');  // 1번 화면: 시작하기 버튼
    const btnReady = document.getElementById('btn-ready');  // 2번 화면: 준비 완료 버튼
    const btnEnd = document.getElementById('btn-end');      // 3번 화면: 운동 종료 버튼
    const btnHome = document.getElementById('btn-home');    // 4번 화면: 홈으로 가기 버튼

    /**
     * 특정 화면 인덱스로 부드럽게 슬라이드 이동하는 함수
     * @param {number} index - 이동할 화면 인덱스 (0: 메인, 1: 가이드, 2: 실시간 분석, 3: 결과 리포트)
     */
    function goToScreen(index) {
        // 1. 슬라이더 컨테이너를 가로로 이동시킵니다.
        // 각 화면은 너비의 25%씩을 차지하고 있으므로 index * 25% 만큼 왼쪽(-)으로 밀어줍니다.
        slider.style.transform = `translateX(-${index * 25}%)`;

        // 2. 왼쪽 데스크톱 가이드 패널의 활성화(active) 클래스를 갱신합니다.
        steps.forEach((step, i) => {
            if (i === index) {
                step.classList.add('active');
            } else {
                step.classList.remove('active');
            }
        });
    }

    // ==========================================
    // 1단계: 메인 화면 -> [스쿼트 코칭 시작하기] 클릭 -> 카메라 가이드 이동
    // ==========================================
    if (btnStart) {
        btnStart.addEventListener('click', () => {
            goToScreen(1);
        });
    }

    // ==========================================
    // 2단계: 카메라 가이드 -> [준비 완료] 클릭 -> 실시간 분석 화면 이동
    // ==========================================
    if (btnReady) {
        btnReady.addEventListener('click', () => {
            goToScreen(2);
        });
    }

    // ==========================================
    // 3단계: 실시간 분석 -> [운동 종료] 클릭 -> 결과 리포트 화면 이동
    // ==========================================
    if (btnEnd) {
        btnEnd.addEventListener('click', () => {
            goToScreen(3);
        });
    }

    // ==========================================
    // 4단계: 결과 리포트 -> [홈으로 가기] 클릭 -> 메인 화면으로 복귀
    // ==========================================
    if (btnHome) {
        btnHome.addEventListener('click', () => {
            goToScreen(0);
        });
    }

    // ==========================================
    // 추가 편의 기능: 
    // 왼쪽 데스크톱 가이드 탭을 직접 마우스로 클릭해도 해당 화면으로 바로 건너뛸 수 있도록 지원합니다.
    // ==========================================
    steps.forEach((step) => {
        step.addEventListener('click', () => {
            // 태그 내 data-step 속성에 지정해 둔 0, 1, 2, 3 인덱스 값을 가져옵니다.
            const targetIndex = parseInt(step.getAttribute('data-step'), 10);
            goToScreen(targetIndex);
        });
    });
});
