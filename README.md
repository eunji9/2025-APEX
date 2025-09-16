# 2025-APEX
<<<<<<< Updated upstream
2025-APEX 🏃
save me..
=======
2025-APEX


9/15 기준 
{
APEX/urls.py/path('api/', include('routing.urls')) 추가.

esp_serial_bridge.py 아두이노 전송 정보형태 변경.

static에 img, dashboard.js(경로연산 화살표 ui, 탈출구 버튼, 리셋버튼) 추가.

templates에 body 부분 svg 코드 추가(경로연산 화살표 ui, 탈출구 버튼, 리셋버튼), 이에 해당하는 css 코드 html 약간 추가.

graph_data.py 프론트 페이지에 맞게 수정.

services.py에 apply_esp_code graph_data.py 변경사항에 맞게 수정

views.py 리셋버튼 적용위해 내용 추가

routing/urls.py  path('api/reset-exclusions/', reset_exclusions_view, name='reset-exclusions'), 추가 (리셋버튼 관련)
}
>>>>>>> Stashed changes
