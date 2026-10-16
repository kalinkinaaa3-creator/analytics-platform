from .load_select_market_tt import Command as CompetitorCommand


class Command(CompetitorCommand):
    source = "ps"
    help = "Collect Select Market PS data through shared parser capacity"
