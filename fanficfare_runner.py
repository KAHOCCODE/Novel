"""Tiến trình FanFicFare cô lập, có tín hiệu tiến độ theo từng chương."""

import json
import logging
import re
import sys
from pathlib import Path


def emit(kind, payload=None):
    message = kind
    if payload is not None:
        message += "\t" + json.dumps(payload, ensure_ascii=False)
    print(message, flush=True)


def build_configuration(url, output_format, allow_mature, interval=3):
    import fanficfare
    from fanficfare import adapters
    from fanficfare.configurable import Configuration

    logging.getLogger("fanficfare").setLevel(logging.WARNING)

    configuration = Configuration(adapters.getConfigSectionsFor(url), output_format)
    defaults_path = Path(fanficfare.__file__).with_name("defaults.ini")
    configuration.read([str(defaults_path)])
    if not configuration.has_section("overrides"):
        configuration.add_section("overrides")

    safe_options = {
        "always_overwrite": "true",
        "slow_down_sleep_time": str(max(2, interval * 2)),
        "is_adult": "true" if allow_mature else "false",
        "fail_on_password": "true",
        "username": "",
        "password": "",
        "include_images": "false",
        "use_browser_cache": "false",
        "use_browser_cache_only": "false",
        "open_pages_in_browser": "false",
        "use_flaresolverr_proxy": "false",
        "use_flaresolverr_session": "false",
        "use_cloudscraper": "false",
        "progressbar": "false",
    }
    for key, value in safe_options.items():
        configuration.set("overrides", key, value)
    configuration.reset_cached_config()
    return configuration


def safe_name(value, fallback, max_length=80):
    """Tạo tên tương thích Windows và tránh đường dẫn quá dài."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    result = (value or fallback)[:max_length].rstrip(" .") or fallback
    if result.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "LPT1", "LPT2", "LPT3", "LPT4"}:
        result = f"_{result}"
    return result


def write_progress_file(path, title, status, detail=""):
    lines = [
        "TIẾN ĐỘ TẢI TRUYỆN",
        "=" * 60,
        f"Tên truyện: {title}",
        f"Trạng thái: {status}",
    ]
    if detail:
        lines.append(detail)
    lines.extend(
        [
            "",
            "Tệp này chỉ dùng để theo dõi và sẽ được xóa khi tải hoàn tất.",
            "Các tệp chương đã tải xong được giữ lại nếu bạn bấm Dừng.",
        ]
    )
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    except OSError:
        # Không để lỗi tệp theo dõi làm hỏng toàn bộ lượt tải.
        pass


def chapter_to_text(html):
    from html2text import html2text

    return html2text(str(html or ""), bodywidth=0).strip()


def write_chapter_file(story_dir, story_title, index, total, title, chapter_url, html):
    width = max(3, len(str(max(1, total))))
    chapter_name = safe_name(title, f"Chương {index}", max_length=78)
    filename = f"{index:0{width}d} - {chapter_name}.txt"
    target = story_dir / filename
    temporary = target.with_suffix(".txt.tmp")
    content = "\n".join(
        [
            story_title,
            f"Chương {index}/{total}: {title}",
            f"Nguồn: {chapter_url}",
            "=" * 60,
            "",
            chapter_to_text(html),
            "",
        ]
    )
    temporary.write_text(content, encoding="utf-8-sig")
    temporary.replace(target)
    return target


def run(url, output_format, allow_mature, interval=3):
    from fanficfare import adapters, writers

    split_chapters = output_format == "chapters"
    writer_format = "txt" if split_chapters else output_format
    clean_url, chapter_begin, chapter_end = adapters.get_url_chapter_range(url)
    configuration = build_configuration(clean_url, writer_format, allow_mature, interval)
    adapter = adapters.getAdapter(configuration, clean_url)
    adapter.setChaptersRange(chapter_begin, chapter_end)

    emit("ND_PHASE", {"status": "Đang đọc thông tin truyện...", "fraction": 0.005})
    story = adapter.getStoryMetadataOnly(get_cover=False)
    title = story.getMetadata("title") or "Truyện chưa rõ tên"
    total = story.getChapterCount()
    story_dir = None
    progress_path = None

    if split_chapters:
        story_dir = Path.cwd() / safe_name(title, "Truyen")
        story_dir.mkdir(parents=True, exist_ok=True)
        progress_path = story_dir / "TIEN_DO.dang-tai.txt"
    else:
        progress_path = Path.cwd() / f"{safe_name(title, 'Truyen')}.dang-tai.txt"

    write_progress_file(
        progress_path,
        title,
        f"Đã nhận diện {total} chương",
        "Đang chuẩn bị tải chương đầu tiên...",
    )
    emit(
        "ND_META",
        {
            "title": title,
            "total": total,
            "status": f"Đã tìm thấy {total} chương",
            "fraction": 0.01,
            "status_file": str(progress_path.resolve()),
            "output_path": str(story_dir.resolve()) if story_dir else "",
            "split_chapters": split_chapters,
        },
    )

    # Publish the exact chapter URL before fetching it (including failures).
    raw_get_chapter = adapter.getChapterTextNum
    def traced_get_chapter(chapter_url, source_index):
        emit("ND_URL", {"url": chapter_url, "index": source_index + 1})
        return raw_get_chapter(chapter_url, source_index)
    adapter.getChapterTextNum = traced_get_chapter

    completed_files = 0

    if split_chapters:
        original_get_chapter = adapter.getChapterTextNum

        def download_and_save_chapter(chapter_url, source_index):
            nonlocal completed_files
            html = original_get_chapter(chapter_url, source_index)
            completed_files += 1
            chapter_title = ""
            if 0 <= source_index < len(adapter.chapterUrls):
                chapter_title = adapter.chapterUrls[source_index].get("title", "")
            write_chapter_file(
                story_dir,
                title,
                completed_files,
                total,
                chapter_title or f"Chương {completed_files}",
                chapter_url,
                html,
            )
            return html

        adapter.getChapterTextNum = download_and_save_chapter

    def notify(percent, _story_url):
        current = min(total, max(1, int(round(percent * total)))) if total else 0
        chapter_title = ""
        if current and current <= len(adapter.chapterUrls):
            chapter_title = adapter.chapterUrls[current - 1].get("title", "")
        output_detail = (
            f"Đã tạo {completed_files} tệp chương trong: {story_dir}"
            if split_chapters
            else "Tệp gộp sẽ xuất hiện sau khi tải đủ chương."
        )
        write_progress_file(
            progress_path,
            title,
            f"Đang tải chương {current}/{total}",
            output_detail,
        )
        emit(
            "ND_PROGRESS",
            {
                "title": title,
                "current": current,
                "total": total,
                "chapter_title": chapter_title,
                "status": (
                    ("Đã lưu đủ tệp chương" if split_chapters else "Đã tải đủ chương, đang ghi tệp...")
                    if current == total
                    else f"Đang tải chương {current}/{total}"
                ),
                "fraction": 0.98 * percent,
                "status_file": str(progress_path.resolve()),
                "output_path": str(story_dir.resolve()) if story_dir else "",
                "files_written": completed_files,
                "split_chapters": split_chapters,
            },
        )

    try:
        if split_chapters:
            adapter.getStory(notification=notify)
            output_path = story_dir.resolve()
            output_filename = ""
        else:
            writer = writers.getWriter(writer_format, configuration, adapter)
            output_filename = writer.getOutputFileName()
            writer.writeStory(forceOverwrite=True, notification=notify)
            output_path = (Path.cwd() / output_filename).resolve()

        try:
            progress_path.unlink(missing_ok=True)
        except OSError:
            pass
        emit(
            "ND_DONE",
            {
                "title": title,
                "current": total,
                "total": total,
                "output_filename": output_filename,
                "output_path": str(output_path),
                "files_written": completed_files,
                "split_chapters": split_chapters,
                "status": "Đã tải xong",
                "fraction": 1.0,
            },
        )
    except Exception as exc:
        write_progress_file(
            progress_path,
            title,
            "TẢI BỊ GIÁN ĐOẠN",
            f"Lỗi: {str(exc) or exc.__class__.__name__}",
        )
        raise


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) not in (4, 5):
        emit("ND_ERROR", {"message": "Tham số bộ tải không hợp lệ."})
        return 2
    try:
        run(sys.argv[1], sys.argv[2].lower(), sys.argv[3] == "1", float(sys.argv[4]) if len(sys.argv) == 5 else 3)
        return 0
    except Exception as exc:
        emit("ND_ERROR", {"message": str(exc) or exc.__class__.__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
