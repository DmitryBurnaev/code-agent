import dataclasses
import random


@dataclasses.dataclass(frozen=True)
class DashboardCounts:
    total_vendors: int
    active_vendors: int


class AdminCounter:

    @classmethod
    async def get_stat(cls) -> DashboardCounts:
        return DashboardCounts(
            total_vendors=random.randint(1, 100),
            active_vendors=random.randint(1, 100),
        )
