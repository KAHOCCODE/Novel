import asyncio
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from plugins.base import BaseCrawler


class FanFicFarePublicCrawler(BaseCrawler):
    """Cầu nối tới FanFicFare cho các truyện đọc công khai.

    Plugin luôn chạy ở chế độ không tương tác, không nhận tài khoản/mật khẩu và
    không cố vượt qua trang đăng nhập, CAPTCHA hay chương trả phí.
    """

    display_name = "Hơn 100 nguồn công khai (FanFicFare)"
    priority = 10
    supports_exact_progress = True
    supports_pause = False

    def __init__(self, log_callback):
        super().__init__(log_callback)
        self.output_format = "txt"
        self.allow_mature = False
        self._domains = set()
        self._sources = []
        self._dependency_error = None
        self._load_source_catalog()

    def _load_source_catalog(self):
        try:
            from fanficfare import adapters

            seen = set()
            for site, examples in adapters.getSiteExamples():
                domain = (site or "").strip().lower()
                if not domain or domain.startswith("test"):
                    continue

                example = ""
                if examples:
                    example = next((item for item in examples if item.startswith("http")), "")

                host = urlparse(example).hostname if example else None
                catalog_host = domain.split("/", 1)[0].lower()
                host = (host or catalog_host).lower()
                host_without_www = host.removeprefix("www.")
                key = (domain, example)
                if key in seen:
                    continue
                seen.add(key)

                self._domains.add(host)
                self._domains.add(host_without_www)
                self._domains.add(catalog_host)
                self._domains.add(catalog_host.removeprefix("www."))
                self._sources.append(
                    {
                        "name": domain,
                        "domain": host_without_www,
                        "provider": "FanFicFare · công khai",
                        "example": example,
                    }
                )

            self._sources.sort(key=lambda item: item["name"].casefold())
        except Exception as exc:
            self._dependency_error = exc

    def get_supported_sources(self):
        return list(self._sources)

    def can_handle(self, url):
        if self._dependency_error:
            return False
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        normalized_host = host.removeprefix("www.")
        return any(
            normalized_host == domain or normalized_host.endswith(f".{domain}")
            for domain in self._domains
        )

    def configure_run(self, **options):
        super().configure_run(**options)
        requested_format = str(options.get("output_format", "TXT · từng chương")).strip().lower()
        format_map = {
            "txt · từng chương": "chapters",
            "từng chương": "chapters",
            "chapters": "chapters",
            "txt": "chapters",
            "txt · gộp": "txt",
            "txt gộp": "txt",
            "epub · gộp": "epub",
            "epub": "epub",
            "html · gộp": "html",
            "html": "html",
        }
        self.output_format = format_map.get(requested_format, "chapters")
        self.allow_mature = bool(options.get("allow_mature", False))

    async def start_download(self, url, save_folder):
        if self._dependency_error:
            raise RuntimeError(
                "Thiếu FanFicFare. Hãy chạy CaiDat.bat để cài đủ thư viện."
            ) from self._dependency_error

        output_dir = Path(save_folder).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        runner_path = Path(__file__).resolve().parent.parent / "fanficfare_runner.py"
        command = [
            sys.executable,
            "-u",
            str(runner_path),
            url,
            self.output_format,
            "1" if self.allow_mature else "0",
            str(self.request_interval),
        ]

        kwargs = {
            "cwd": str(output_dir),
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        format_label = "TXT từng chương" if self.output_format == "chapters" else self.output_format.upper()
        self.log(f"Nguồn công khai đã nhận diện · định dạng {format_label}")
        self.report_progress(
            fraction=0.0,
            title="Đang nhận diện truyện...",
            status="Đang kết nối nguồn truyện",
            detail="Đang chuẩn bị thư mục kết quả...",
            indeterminate=False,
        )
        process = await asyncio.create_subprocess_exec(*command, **kwargs)

        error_message = ""
        stop_sent = False
        status_file_path = None
        try:
            while True:
                if self.should_stop() and process.returncode is None and not stop_sent:
                    process.terminate()
                    stop_sent = True
                    self.log("Đang dừng tiến trình tải an toàn...")

                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=0.25)
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

                if line:
                    message = line.decode("utf-8", errors="replace").strip()
                    if message.startswith("ND_URL\t"):
                        try:
                            item = json.loads(message.split("\t", 1)[1])
                            self.track_url(item['url'])
                            self.log(f"[ĐANG TẢI] Chương {item.get('index', '?')} · {item['url']}")
                        except (ValueError, KeyError, TypeError):
                            self.log(message)
                        continue
                    if message.startswith(("ND_PHASE\t", "ND_META\t", "ND_PROGRESS\t", "ND_DONE\t")):
                        kind, raw_payload = message.split("\t", 1)
                        try:
                            payload = json.loads(raw_payload)
                            if payload.get("status_file"):
                                status_file_path = Path(payload["status_file"])
                            current = payload.get("current")
                            total = payload.get("total")
                            chapter_title = payload.get("chapter_title", "")
                            output_path = payload.get("output_path")
                            split_chapters = bool(payload.get("split_chapters"))
                            if kind == "ND_DONE" and output_path:
                                if split_chapters:
                                    count = payload.get("files_written", total or 0)
                                    payload["detail"] = f"{count} tệp chương · {output_path}"
                                else:
                                    payload["detail"] = f"Đã lưu: {output_path}"
                            elif kind == "ND_META" and output_path:
                                payload["detail"] = f"Thư mục truyện: {output_path}"
                            elif current is not None and total:
                                if split_chapters:
                                    count = payload.get("files_written", current)
                                    detail = f"Đã lưu {count}/{total} tệp"
                                else:
                                    detail = f"Chương {current}/{total} · tệp gộp tạo khi hoàn tất"
                                if chapter_title:
                                    detail += f" · {chapter_title}"
                                payload["detail"] = detail
                            payload["indeterminate"] = False
                            self.report_progress(**payload)
                        except (ValueError, TypeError):
                            self.log(message)
                    elif message.startswith("ND_ERROR\t"):
                        try:
                            error_message = json.loads(message.split("\t", 1)[1]).get("message", "")
                        except (ValueError, TypeError):
                            error_message = message
                    elif message:
                        self.log(message)
                else:
                    break

            return_code = await process.wait()
        finally:
            if self.should_stop() and process.returncode is None:
                process.kill()
                await process.wait()

        if self.should_stop():
            if status_file_path:
                try:
                    with status_file_path.open("a", encoding="utf-8-sig") as handle:
                        handle.write("\nTrạng thái: ĐÃ DỪNG THEO YÊU CẦU\n")
                except OSError:
                    pass
            return
        if return_code != 0:
            raise RuntimeError(
                (error_message + ". " if error_message else "")
                + "Nguồn từ chối tải hoặc truyện không ở trạng thái công khai. "
                "Ứng dụng không vượt đăng nhập, CAPTCHA hay chương trả phí."
            )

        self.log(f"Đã lưu truyện vào: {output_dir}")

        return {"completed": True, "output_path": str(output_dir)}
