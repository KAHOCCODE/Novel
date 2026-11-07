"""Extract the story text used for both browser validation and saved parts."""
import re

from bs4 import BeautifulSoup


def clean_content(soup):
    body = soup.select_one('#bookContentBody')
    if body is None:
        raise RuntimeError('Không tìm thấy #bookContentBody; chưa lưu chương này.')
    body = BeautifulSoup(str(body), 'html.parser')
    for node in body.select('script, style, iframe, noscript, form, button, .tpm-unit, .adsbygoogle, .chapter-part, [id^="tpads_"]'):
        node.decompose()
    for node in body.find_all('br'):
        node.replace_with('\n')
    # Block boundaries, preserve inline words and text outside <p> as well.
    for node in body.find_all(['p', 'div']):
        node.insert_before('\n\n')
        node.insert_after('\n\n')
    text = body.get_text().strip()
    text = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', text)
    if not text:
        raise RuntimeError('Phần truyện rỗng; chưa đánh dấu hoàn tất.')
    return text
