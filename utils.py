import re
import os
import unicodedata

def safe_filename(name):
    """Làm sạch tên file/folder"""
    name = re.sub(r"[\x00-\x1F]", "", name)
    name = ''.join(c for c in name if not unicodedata.category(c).startswith("Cs"))
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = " ".join(name.split()).strip().rstrip(".")
    name = name[:150].rstrip(" .") or "Unknown"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I):
        name = "_" + name
    return name

def save_metadata(folder_path, title, author="", url="", desc=""):
    """Lưu thông tin truyện"""
    filepath = os.path.join(folder_path, "thong_tin_truyen.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"TÊN TRUYỆN: {title}\n")
        f.write(f"TÁC GIẢ: {author}\n")
        f.write(f"NGUỒN: {url}\n")
        f.write("-" * 30 + "\n")
        f.write(desc)
    return filepath