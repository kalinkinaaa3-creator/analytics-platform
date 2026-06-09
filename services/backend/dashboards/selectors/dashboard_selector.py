from dashboards.engine.v3.dashboard_engine import DashboardEngineV3


engine = DashboardEngineV3()


def get_dashboard_data(dashboard):
    return engine.build_dashboard(dashboard)