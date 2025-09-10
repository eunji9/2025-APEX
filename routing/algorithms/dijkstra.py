import heapq
from typing import Dict, List, Tuple, Optional

INF = float('inf')

def dijkstra_multisource(
    adj: Dict[str, List[Tuple[str, float]]],
    sources: List[str]
):
    dist = {node: INF for node in adj.keys()}
    prev = {node: None for node in adj.keys()}
    src_of = {node: None for node in adj.keys()}

    pq = []
    for s in sources:
        if s in adj:
            dist[s] = 0.0
            src_of[s] = s
            heapq.heappush(pq, (0.0, s))

    while pq:
        d, u = heapq.heappop(pq)
        if d != dist[u]:
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                src_of[v] = src_of[u]
                heapq.heappush(pq, (nd, v))
    return dist, prev, src_of

def reconstruct_path(prev: Dict[str, Optional[str]], target: str) -> List[str]:
    path = []
    cur = target
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return list(reversed(path))