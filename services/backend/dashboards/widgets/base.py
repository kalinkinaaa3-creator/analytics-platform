from abc import ABC, abstractmethod


class BaseWidget(ABC):

    @abstractmethod
    def build(self, rows: list[dict], params: dict):
        """
        rows: нормализованные данные
        params: настройки виджета (x, y, group, etc.)
        """
        pass