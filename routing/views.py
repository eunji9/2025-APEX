from django.shortcuts import render

# Create your views here.
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from routing.forms import ShortestPathForm
from routing.models import FloorState
from routing.services import shortest_to_target, distances_all, apply_esp_code


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