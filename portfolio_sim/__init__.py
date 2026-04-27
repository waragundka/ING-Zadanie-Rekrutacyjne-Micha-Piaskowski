"""Currency basket investment simulator backed by NBP exchange-rate data."""
from portfolio_sim.allocation import Allocation
from portfolio_sim.audit import record_run
from portfolio_sim.metrics import PortfolioMetrics, compute_metrics
from portfolio_sim.nbp_client import NBPAPIError, NBPClient
from portfolio_sim.portfolio import PortfolioSimulator, SimulationResult

__all__ = [
    "Allocation",
    "NBPAPIError",
    "NBPClient",
    "PortfolioMetrics",
    "PortfolioSimulator",
    "SimulationResult",
    "compute_metrics",
    "record_run",
]

__version__ = "1.0.0"
