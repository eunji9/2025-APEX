from django.db import models

class Floor(models.Model):
    level = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Floor {self.level}"

class Node(models.Model):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='nodes')
    label = models.CharField(max_length=32)

    class Meta:
        unique_together = ('floor', 'label')
        indexes = [models.Index(fields=['floor', 'label'])]

    def __str__(self):
        return f"F{self.floor.level}:{self.label}"

class Edge(models.Model):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='edges')
    u = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='edges_u')
    v = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='edges_v')
    weight = models.FloatField()
    bidirectional = models.BooleanField(default=True)

    def __str__(self):
        return f"F{self.floor.level}:{self.u.label}-{self.v.label}({self.weight})"

class StartNode(models.Model):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='start_nodes')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='as_start')

    class Meta:
        unique_together = ('floor', 'node')
        indexes = [models.Index(fields=['floor'])]

class FloorState(models.Model):
    floor = models.OneToOneField(Floor, on_delete=models.CASCADE, related_name='state')
    last_code = models.CharField(max_length=1, blank=True, null=True)      # '1'|'2'|'3'
    exclude_u = models.CharField(max_length=32, blank=True, null=True)     # '1'
    exclude_v = models.CharField(max_length=32, blank=True, null=True)     # '2'
    last_result = models.JSONField(default=dict, blank=True)               # distances_all() 결과
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FloorState(F{self.floor.level}, code={self.last_code}, excl=({self.exclude_u},{self.exclude_v}))"