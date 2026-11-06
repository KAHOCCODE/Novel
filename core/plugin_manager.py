import importlib.util
import inspect
import sys
from pathlib import Path
from plugins.base import BaseCrawler

class PluginManager:
    def __init__(self, log_callback):
        self.plugins = []
        self.plugin_map = {}
        self.source_catalog = []
        self.log = log_callback
        self.base_dir = Path(__file__).resolve().parent.parent
        self.plugin_dir = self.base_dir / "plugins"
        self.load_plugins()

    def load_plugins(self):
        self.plugins.clear()
        self.plugin_map.clear()
        self.source_catalog.clear()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.log("Đang quét plugin...")

        for file in sorted(self.plugin_dir.glob("*.py")):
            if file.name in {"base.py", "__init__.py", "tinhngoncoc.py"}:
                continue
            self._load_one_file(file)

        self.plugins.sort(key=lambda item: getattr(item, "priority", 100), reverse=True)
        self._build_source_catalog()
        self.log(
            f"Sẵn sàng: {len(self.plugins)} plugin · "
            f"{len(self.source_catalog)} nguồn được nhận diện."
        )

    def _load_one_file(self, filepath):
        try:
            module_name = f"plugin_{filepath.stem}_{int(filepath.stat().st_mtime_ns)}"
            spec = importlib.util.spec_from_file_location(module_name, str(filepath))
            if spec is None or spec.loader is None:
                raise RuntimeError("Không thể tạo module plugin.")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            exec(compile(filepath.read_text(encoding="utf-8-sig"), str(filepath), "exec"), module.__dict__)
            found = 0

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BaseCrawler or not issubclass(obj, BaseCrawler) or obj.__module__ != module.__name__:
                    continue
                instance = obj(self.log)
                display_name = instance.get_display_name()
                if display_name in self.plugin_map:
                    display_name = f"{display_name} ({filepath.stem})"
                instance.plugin_file = str(filepath)
                self.plugins.append(instance)
                self.plugin_map[display_name] = instance
                self.log(f"Đã nạp: {display_name}")
                found += 1

            if found == 0:
                self.log(f"File {filepath.name} không chứa plugin hợp lệ.")
        except Exception as exc:
            self.log(f"Không thể nạp {filepath.name}: {exc}")

    def _build_source_catalog(self):
        seen = set()
        for crawler in self.plugins:
            try:
                sources = crawler.get_supported_sources()
            except Exception as exc:
                self.log(f"Không đọc được danh mục của {crawler.get_display_name()}: {exc}")
                continue

            for source in sources:
                item = {
                    "name": str(source.get("name") or crawler.get_display_name()),
                    "domain": str(source.get("domain") or "Plugin chuyên biệt"),
                    "provider": str(source.get("provider") or "Plugin"),
                    "example": str(source.get("example") or ""),
                }
                key = (item["name"].casefold(), item["domain"].casefold(), item["provider"].casefold())
                if key not in seen:
                    seen.add(key)
                    self.source_catalog.append(item)

        self.source_catalog.sort(key=lambda item: (item["provider"], item["name"].casefold()))

    def find_handler(self, url):
        from urllib.parse import urlparse
        if (urlparse(url).hostname or '').lower().removeprefix('www.') == 'tinhngoncoc.net': return None
        for crawler in self.plugins:
            try:
                if crawler.can_handle(url):
                    return crawler
            except Exception as exc:
                self.log(f"Plugin {crawler.get_display_name()} lỗi khi kiểm tra URL: {exc}")
        return None

    def get_plugin_names(self):
        return list(self.plugin_map.keys())

    def get_source_catalog(self):
        return list(self.source_catalog)

    def plugin_count(self):
        return len(self.plugins)

    def source_count(self):
        return len(self.source_catalog)


