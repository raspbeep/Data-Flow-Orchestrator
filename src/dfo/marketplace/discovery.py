from importlib.metadata import entry_points

from dfo.core.exceptions import PluginError
from dfo.plugins.base import Plugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def get(self, name: str) -> Plugin:
        if name not in self._plugins:
            raise ValueError(
                f"Plugin '{name}' not found. Available plugins: {self._plugins}"
            )

        return self._plugins[name]

    def list_plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    def discover(self) -> None:
        plugin_eps = entry_points(group="dfo.plugins")
        for ep in plugin_eps:
            plugin_class = ep.load()
            plugin = plugin_class()

            if not isinstance(plugin, Plugin):
                raise PluginError(
                    "Failed to load plugin (Incorrect class of the object)."
                )

            self._plugins[plugin.name] = plugin
