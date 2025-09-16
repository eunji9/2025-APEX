import json
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt

from routing.forms import ShortestPathForm
from routing.models import FloorState
from routing.services import shortest_to_target, distances_all, apply_esp_code, reset_exclusions



@require_GET
def shortest_path_view(request):
    """
    GET /api/shortest-path/?floor=1&target=14
    GET /api/shortest-path/?floor=3
    GET /api/shortest-path/?floor=2&sources=3,13,9
    """
    form = ShortestPathForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400, json_dumps_params={"ensure_ascii": False})

    floor = form.cleaned_data["floor"]
    target = form.cleaned_data.get("target")
    sources = form.sources_list()

    data = shortest_to_target(floor, target, sources) if target else distances_all(floor, sources)
    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_POST
def esp_event_view(request):
    """
    ESP32/브리지 등에서 POST {"code": "1".."6"}
    → 누적 제외 갱신 + 해당 층 재계산
    """
    try:
        payload = json.loads((request.body or b"").decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    code = str(payload.get("code", "")).strip()
    res = apply_esp_code(code)
    status_code = 200 if res.get("status") in ("ok", "no_change") else 400
    return JsonResponse(res, status=status_code, json_dumps_params={"ensure_ascii": False})


@require_GET
def dashboard_text(request):
    """
    텍스트 대시보드 (/api/dashboard.txt)
    각 층의 'SPT(최단경로 트리) 간선 방향'만 한 줄로 출력.
    형식: nF (u, v, d), (u, v, d), ...
      - d=0: 저장된 정방향(u→v)
      - d=1: 반대방향(v→u)
    """
    states = FloorState.objects.select_related("floor").order_by("floor__level")
    if not states.exists():
        return HttpResponse("No state. Send ESP event first.\n", content_type="text/plain; charset=utf-8")

    lines = []
    for st in states:
        lr = st.last_result or {}
        triples = lr.get("all_edges_dir", [])

        if not triples:
            # 결과가 없다면 즉시 계산해서 채워줌(초기 1회)
            res = distances_all(level=st.floor.level)
            st.last_result = res
            st.save(update_fields=["last_result", "updated_at"])
            triples = res.get("all_edges_dir", [])

        parts = [f"({u}, {v}, {d})" for u, v, d in triples]
        lines.append(f"{st.floor.level}F " + ", ".join(parts))

    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")



# 관리자용 view
@require_GET
def floor1_page(request):
    """첫 화면: 1층 도면 페이지 (HTML)"""
    # 페이지에서 바로 그릴 수 있도록 1층 데이터 미리 가져가도 되고
    # (템플릿에서 fetch로 /routing/shortest-path/ 를 호출해도 됨)
    level = 1
    data = distances_all(level, sources=[])  # 필요시 sources 지정
    ctx = {
        "level": level,
        "graph_data": data,  # 템플릿에서 JSON 직렬화해서 사용
    }
    return render(request, "routing/floor1.html", ctx)

@require_GET
def dashboard_page(request):
    """대시보드(HTML) 버전: 텍스트가 아닌 테이블/뷰로 보여주기"""
    states = FloorState.objects.select_related("floor").order_by("floor__level")
    rows = []
    for st in states:
        lr = st.last_result or {}
        triples = lr.get("all_edges_dir", [])
        rows.append({"level": st.floor.level, "edges": triples})
    return render(request, "routing/dashboard.html", {"rows": rows})



# 리셋버튼 관련 -->

def _parse_floors(request):
    """
    floors를 [1,2,3] 형태로 파싱
    - GET:  /api/reset-exclusions/?floors=1,2,3
    - POST: {"floors":[1,2,3]} 또는 {"floors": "1,2,3"}
    생략 시 None(= 전체 층)
    """
    floors = None
    if request.method == 'GET':
        q = request.GET.get('floors')
        if q:
            floors = [int(x) for x in q.split(',') if x.strip().isdigit()]
    else:  # POST
        try:
            data = json.loads((request.body or b'{}').decode('utf-8'))
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')
        val = data.get('floors')
        if isinstance(val, (list, tuple)):
            floors = [int(x) for x in val if str(x).isdigit()]
        elif isinstance(val, str):
            floors = [int(x) for x in val.split(',') if x.strip().isdigit()]
    return floors

@csrf_exempt                        # CSRF 없이 쓰려면 유지 (POST 쓸 때 편함). GET만 쓸 거면 굳이 없어도 됨.
@require_http_methods(['GET', 'POST'])
def reset_exclusions_view(request):
    floors = _parse_floors(request)
    if isinstance(floors, HttpResponseBadRequest):
        return floors

    # 핵심: services.py 의 reset_exclusions 실행 (네가 올린 함수 그대로 사용)
    res = reset_exclusions(levels=floors)  # {"status":"ok", "floors":[...]}
    return JsonResponse({"ok": True, **res})