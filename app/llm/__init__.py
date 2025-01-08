from app.models import SnookerPlayer


class FewShotData:
    """Abstract class - Implementations should contain few-shot data for LLM."""

    def __init__(self) -> None:
        pass

    @property
    def players(self) -> list[SnookerPlayer]:
        raise NotImplementedError

    @property
    def examples(self) -> list[dict]:
        raise NotImplementedError