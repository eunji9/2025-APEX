from typing import Dict, List, Tuple, Optional, Iterable
from collections import defaultdict
from django.db import transaction
from routing.models import Floor, Edge, StartNode, FloorState
from routing.algorithms.dijkstra import dijkstra_multisource, reconstruct_path

# ---------- 내부 유틸 ----------

def _collect_excluded_edges(floor: Floor) -> List[Tuple[str, str]]:
    """
    누적 제외 간선 목록을 수집한다.
    - 호환용 단일 필드(exclude_u/exclude_v)
    - last_result JSON의 excluded_edges [[u,v], ...]
    """
    excludes = set()
    state = getattr(floor, 'state', None)
    if not state:
        return []

    if state.exclude_u and state.exclude_v:
        excludes.add((state.exclude_u, state.exclude_v))

    lr = state.last_result or {}
    for pair in lr.get('excluded_edges', []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            excludes.add((str(pair[0]), str(pair[1])))

    return list(excludes)


def _edge_dir_index(level: int) -> Dict[Tuple[str, str], int]:
    """
    DB에 저장된 간선 방향 기준으로 (u->v)=0, (v->u)=1 인덱스 생성.
    """
    floor = Floor.objects.get(level=level)
    idx: Dict[Tuple[str, str], int] = {}
    for e in Edge.objects.filter(floor=floor).select_related('u', 'v'):
        u, v = e.u.label, e.v.label
        idx[(u, v)] = 0  # 정방향
        if e.bidirectional:
            idx[(v, u)] = 1  # 반대방향
    return idx


def edges_dir_from_prev(level: int, prev: Dict[str, Optional[str]]) -> List[List[str]]:
    """
    다익스트라 prev 트리로부터 SPT의 모든 간선을 방향과 함께 반환.
    반환 형태: [[u, v, d], ...]  (u=parent, v=child, d=0 정방향 / 1 반대방향 / -1 미정)
    """
    idx = _edge_dir_index(level)
    triples: List[List[str]] = []
    for v, p in prev.items():
        if p is None:
            continue  # 소스 노드
        d = idx.get((p, v))
        if d is None:
            d = idx.get((v, p))
            if d is None:
                d = -1  # 정의되지 않은 경우(이상 케이스)
        triples.append([str(p), str(v), int(d)])  # JSON 직렬화 안전
    # 보기 좋게 정렬
    triples.sort(key=lambda t: (len(t[0]), t[0], len(t[1]), t[1]))
    return triples


def directions_for_path(level: int, path_nodes: List[str]) -> List[List[str]]:
    """
    단일 경로에 대한 (u,v,d) 나열. (호환용: target 기반 응답 등에 사용 가능)
    """
    if not path_nodes or len(path_nodes) < 2:
        return []
    idx = _edge_dir_index(level)
    triples: List[List[str]] = []
    for a, b in zip(path_nodes[:-1], path_nodes[1:]):
        d = idx.get((a, b))
        if d is None:
            d = idx.get((b, a))
            if d is None:
                d = -1
        triples.append([str(a), str(b), int(d)])
    return triples


# ---------- 그래프/연산 ----------

def build_adj_for_floor(level: int, apply_overrides: bool = True) -> Dict[str, List[Tuple[str, float]]]:
    """
    층의 인접 리스트를 구성한다. apply_overrides=True인 경우 누적 제외 간선을 제거한다.
    """
    floor = Floor.objects.get(level=level)
    adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    # 모든 간선 로드
    edges = Edge.objects.filter(floor=floor).select_related('u', 'v')
    for e in edges:
        u, v, w = e.u.label, e.v.label, float(e.weight)
        adj[u].append((v, w))
        if e.bidirectional:
            adj[v].append((u, w))
        # 키 강제 생성
        if u not in adj:
            adj[u] = []
        if v not in adj:
            adj[v] = []

    # 누적 제외 적용(양방향 제거)
    if apply_overrides:
        for ex_u, ex_v in _collect_excluded_edges(floor):
            adj[ex_u] = [(nb, w) for (nb, w) in adj.get(ex_u, []) if nb != ex_v]
            adj[ex_v] = [(nb, w) for (nb, w) in adj.get(ex_v, []) if nb != ex_u]

    return dict(adj)


def default_sources_for_floor(level: int) -> List[str]:
    floor = Floor.objects.get(level=level)
    return list(StartNode.objects.filter(floor=floor).values_list('node__label', flat=True))


def shortest_to_target(level: int, target: str, sources: Optional[List[str]] = None) -> Dict:
    """
    단일 타겟에 대한 최단경로 및 방향(호환용).
    """
    adj = build_adj_for_floor(level, apply_overrides=True)
    sources = sources or default_sources_for_floor(level)
    dist, prev, src_of = dijkstra_multisource(adj, sources)

    if target not in dist:
        raise ValueError(f"Unknown target node '{target}' on floor {level}")

    path = reconstruct_path(prev, target)
    floor = Floor.objects.get(level=level)
    excluded = _collect_excluded_edges(floor)

    return {
        "floor": level,
        "sources": sources,
        "target": target,
        "from_source": src_of[target],
        "cost": dist[target],
        "path": path,
        "excluded_edge": excluded[-1] if excluded else None,
        "excluded_edges": excluded,
        "repr_path": path,
        "repr_edges_dir": directions_for_path(level, path),
    }


def distances_all(level: int, sources: Optional[List[str]] = None) -> Dict:
    """
    층의 전체 다익스트라 실행 결과를 반환.
    - distances: 각 노드까지 거리
    - closest_source: 각 노드를 최단으로 만든 출발노드
    - all_edges_dir: 모든 노드까지의 SPT를 이루는 간선들의 (u,v,d) 목록
    - excluded_edges: 누적 제외 목록 (상태 공유)
    """
    adj = build_adj_for_floor(level, apply_overrides=True)
    sources = sources or default_sources_for_floor(level)
    dist, prev, src_of = dijkstra_multisource(adj, sources)

    floor = Floor.objects.get(level=level)
    excluded = _collect_excluded_edges(floor)

    all_edges_dir = edges_dir_from_prev(level, prev)

    return {
        "floor": level,
        "sources": sources,
        "distances": dist,
        "closest_source": src_of,
        "excluded_edge": excluded[-1] if excluded else None,  # 호환용
        "excluded_edges": excluded,                           # 누적 목록
        "all_edges_dir": all_edges_dir,                       # ✅ 대시보드/ESP 전송용 핵심
    }


# ---------- ESP 신호 처리 ----------

def apply_esp_code(code: str) -> Dict:
    """
    ESP32에서 수신한 코드에 따라 누적 제외 간선을 갱신하고 해당 층을 재계산한다.
      '1' -> 1층 (1,2) 제외
      '2' -> 2층 (1,2) 제외
      '3' -> 3층 (1,2) 제외
      '4' -> 1층 (9,10) 제외
      '5' -> 2층 (8,9) 제외
      '6' -> 3층 (7,8) 제외
    """
    MAP = {
        '1': (1, '1', '2'),
        '2': (2, '1', '2'),
        '3': (3, '1', '2'),
        '4': (1, '9', '10'),
        '5': (2, '8', '9'),
        '6': (3, '7', '8'),
    }
    if code not in MAP:
        return {"status": "invalid"}

    level, u, v = MAP[code]

    with transaction.atomic():
        floor = Floor.objects.select_for_update().get(level=level)
        state, _ = FloorState.objects.get_or_create(floor=floor)

        # 누적 제외 목록 갱신(중복 방지)
        lr = state.last_result or {}
        excluded = lr.get('excluded_edges', [])
        if [u, v] not in excluded and [v, u] not in excluded:
            excluded.append([u, v])
        lr['excluded_edges'] = excluded

        # 호환 필드 유지(사용 안하더라도 최신값 저장)
        state.last_code = code
        state.exclude_u = u
        state.exclude_v = v
        state.save()

        # 재계산 & 저장
        result = distances_all(level=level)
        state.last_result = result
        state.save(update_fields=['last_result', 'updated_at', 'last_code', 'exclude_u', 'exclude_v'])

    return {"status": "ok", "floor": level, "excluded_edge": [u, v], "result": result}


# ---------- 브리지/대시보드용 포맷 ----------

def floor_edge_dirs_line(level: int) -> str:
    """
    'nF (u,v,d), (u,v,d), ...' 한 줄 생성 (대시보드/ESP 전송 포맷)
    - 각 층의 SPT를 구성하는 모든 간선의 방향만 포함
    """
    floor = Floor.objects.get(level=level)
    state = getattr(floor, 'state', None)
    if not state or not state.last_result:
        res = distances_all(level=level)
        if state:
            state.last_result = res
            state.save(update_fields=['last_result', 'updated_at'])

    triples = (floor.state.last_result or {}).get('all_edges_dir', [])
    parts = [f"({a},{b},{d})" for a, b, d in triples]
    return f"{level}F " + ",".join(parts)



def reset_exclusions(levels: Optional[Iterable[int]] = None) -> Dict:
    """
    지정한 층(들)의 누적 제외 간선을 초기화하고, 최신 결과를 재계산해서 저장한다.
    levels=None 이면 모든 층을 초기화.
    반환: {"status":"ok", "floors":[1,2,...]}
    """
    if levels is None:
        floors_qs = Floor.objects.all().order_by('level')
    else:
        floors_qs = Floor.objects.filter(level__in=list(levels)).order_by('level')

    done = []
    for floor in floors_qs:
        with transaction.atomic():
            state, _ = FloorState.objects.select_for_update().get_or_create(floor=floor)

            # 1) 제외 목록/호환 필드 초기화
            lr = state.last_result or {}
            lr['excluded_edges'] = []  # 누적 제외 비우기
            state.last_result = lr
            state.last_code = None
            state.exclude_u = None
            state.exclude_v = None
            state.save(update_fields=['last_result', 'last_code', 'exclude_u', 'exclude_v', 'updated_at'])

            # 2) 제외 없이 재계산하여 저장
            fresh = distances_all(level=floor.level)   # _collect_excluded_edges()가 빈 상태이므로 제외 없음
            state.last_result = fresh
            state.save(update_fields=['last_result', 'updated_at'])
            done.append(floor.level)

    return {"status": "ok", "floors": done}