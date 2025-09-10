from django.core.management.base import BaseCommand
from routing.models import Floor, Node, Edge, StartNode, FloorState
from routing.graph_data import FLOOR_EDGES, DEFAULT_SOURCES

class Command(BaseCommand):
    help = "Seed floors/nodes/edges/start-nodes from routing.graph_data (no data migrations)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Seeding graph…"))
        for level, edges in FLOOR_EDGES.items():
            floor, _ = Floor.objects.get_or_create(level=level, defaults={'name': f'{level}F'})

            labels = set()
            for u, v, _ in edges:
                labels.add(u); labels.add(v)
            labels.update(DEFAULT_SOURCES.get(level, []))

            label_to_node = {}
            for lab in sorted(labels, key=lambda x: (len(x), x)):
                node, _ = Node.objects.get_or_create(floor=floor, label=lab)
                label_to_node[lab] = node

            for u, v, w in edges:
                Edge.objects.get_or_create(floor=floor,
                                           u=label_to_node[u],
                                           v=label_to_node[v],
                                           weight=w,
                                           bidirectional=True)

            StartNode.objects.filter(floor=floor).delete()
            for src in DEFAULT_SOURCES.get(level, []):
                StartNode.objects.get_or_create(floor=floor, node=label_to_node[src])

            FloorState.objects.get_or_create(floor=floor)

            self.stdout.write(self.style.SUCCESS(
                f"  Floor {level}: nodes={len(labels)}, edges={len(edges)}, starts={len(DEFAULT_SOURCES.get(level, []))}"
            ))
        self.stdout.write(self.style.SUCCESS("Done."))