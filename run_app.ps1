# =================================================================
#            FitCheck AI MVP v1 실행기 (PowerShell)
# =================================================================
# 초보자분들을 위해 가상환경 세팅 및 앱 구동 단계를 자동화한 스크립트입니다.

# 인코딩 한글 출력 호환성 설정 (UTF-8)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "            FitCheck AI MVP v1 실행기 (PS)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "가상환경 설정 및 필수 라이브러리 세팅 후 앱을 구동합니다." -ForegroundColor Gray
Write-Host ""

# 1. 가상환경(.venv) 확인 및 생성
if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] 가상환경(.venv)이 존재하지 않습니다. 새로 생성합니다..." -ForegroundColor Yellow
    try {
        python -m venv .venv
        Write-Host "[SUCCESS] 가상환경(.venv) 생성 성공!" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] 가상환경 생성 과정에서 오류가 발생했습니다." -ForegroundColor Red
        Write-Host "컴퓨터에 Python이 설치되어 있고 시스템 경로(PATH)에 연동되어 있는지 확인바랍니다." -ForegroundColor Yellow
        Read-Host "종료하려면 엔터 키를 누르세요..."
        exit
    }
} else {
    Write-Host "[INFO] 가상환경(.venv) 폴더를 감지했습니다." -ForegroundColor Green
}
Write-Host ""

# 2. 가상환경 활성화
Write-Host "[INFO] 가상환경 활성화를 시도합니다..." -ForegroundColor Yellow
try {
    . .venv\Scripts\Activate.ps1
    Write-Host "[SUCCESS] 가상환경 활성화 완료!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] PowerShell 보안 실행 정책 제한으로 활성화에 실패했습니다." -ForegroundColor Red
    Write-Host "원인: 윈도우 기본 정책상 서명되지 않은 파워쉘 스크립트 실행이 차단되어 있을 수 있습니다." -ForegroundColor Yellow
    Write-Host "해결 방안: run_app.bat 파일을 이용하시거나, 파워쉘을 관리자 권한으로 열어 'Set-ExecutionPolicy RemoteSigned'를 치시면 해결됩니다." -ForegroundColor Cyan
    Read-Host "종료하려면 엔터 키를 누르세요..."
    exit
}
Write-Host ""

# 3. pip 업데이트 및 라이브러리(requirements.txt) 설치
Write-Host "[INFO] pip 도구 및 필수 라이브러리 패키지를 자동 설치합니다..." -ForegroundColor Yellow
try {
    python -m pip install --upgrade pip
    pip install -r app/requirements.txt
    Write-Host "[SUCCESS] 모든 필수 패키지 구성 완료!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] 라이브러리 패키지 다운로드 중 오류가 발생했습니다. 인터넷 회선 상태를 확인해주세요." -ForegroundColor Red
    Read-Host "종료하려면 엔터 키를 누르세요..."
    exit
}
Write-Host ""

# 4. Streamlit 구동
Write-Host "[INFO] FitCheck AI 웹 어플리케이션을 구동합니다..." -ForegroundColor Yellow
Write-Host "[INFO] 브라우저 창이 자동으로 켜지지 않을 시 다음 주소를 입력하세요: http://localhost:8501" -ForegroundColor Yellow
Write-Host ""

try {
    python -m streamlit run app/main.py
} catch {
    Write-Host "[ERROR] Streamlit 실행이 중단되었습니다." -ForegroundColor Red
}

Read-Host "종료하려면 엔터 키를 누르세요..."
