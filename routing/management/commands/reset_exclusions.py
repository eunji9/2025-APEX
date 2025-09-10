from django.core.management.base import BaseCommand
from routing.services import reset_exclusions

class Command(BaseCommand):
    help = "Reset excluded edges (blocked edges) for given floors or all."

    def add_arguments(self, parser):
        parser.add_argument('--floors', nargs='*', type=int,
                            help="Floors to reset, e.g., --floors 1 3 (omit to reset all)")

    def handle(self, *args, **opts):
        floors = opts.get('floors')
        res = reset_exclusions(levels=floors)
        self.stdout.write(self.style.SUCCESS(f"Reset done: floors={res.get('floors')}"))