"""
02_fetch_index.py — 抓取索引页，获取所有通报链接

用法:
  python scripts/02_fetch_index.py              # 抓所有页
  python scripts/02_fetch_index.py --max-pages 3  # 只抓前3页
"""
import argparse
import datetime
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urljoin
import sys

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_db_path

BASE_URL = "https://www.mot.gov.cn/zhuanti/wuliubtbc/qingkuangtongbao_wuliu/"
INDEX_FIRST = BASE_URL + "index.html"
INDEX_PAGE = BASE_URL + "index_{n}.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.mot.gov.cn/zhuanti/wuliubtbc/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# 通报链接正则：匹配路径中带年月的链接（兼容相对路径 ./YYYYMM/tNNN 和绝对路径）
REPORT_HREF_RE = re.compile(r"\d{6}/t\d+")


def fetch_page(url: str) -> tuple[str | None, str, str]:
    """返回 (html_text, resp_encoding, apparent_encoding)"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"[fetch_index] DEBUG: HTTP状态={resp.status_code}, Content-Type={resp.headers.get('Content-Type','?')}")
        if resp.status_code == 404:
            return None, "", ""
        resp.raise_for_status()
        apparent = resp.apparent_encoding or "utf-8"
        resp.encoding = apparent
        return resp.text, resp.encoding, apparent
    except Exception as e:
        print(f"[fetch_index] 请求失败 {url}: {e}")
        return None, "", ""


def parse_links(html: str, page_url: str) -> list[dict]:
    """从索引页 HTML 解析通报链接列表"""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    news_li = soup.find_all("li", class_="news_title")
    all_li = soup.find_all("li")
    print(f"[fetch_index] DEBUG parse_links: 总<li>={len(all_li)}, class=news_title的<li>={len(news_li)}")

    for li in soup.find_all("li"):
        a = li.find("a", href=REPORT_HREF_RE)
        if not a:
            continue
        href = a.get("href", "")
        # 补全 URL（用 urljoin 正确处理相对路径 ./YYYYMM/tNNN.html）
        url = urljoin(page_url, href)

        title = a.get_text(strip=True).lstrip("·").strip()

        # 从 li 文本中提取日期 [YYYY-MM-DD]
        li_text = li.get_text()
        date_m = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", li_text)
        discovered_at = date_m.group(1) if date_m else datetime.date.today().isoformat()

        results.append(
            {
                "url": url,
                "title": title,
                "index_page": page_url,
                "discovered_at": discovered_at,
            }
        )

    return results


def insert_links(conn: sqlite3.Connection, links: list[dict]) -> int:
    new_count = 0
    for link in links:
        cur = conn.execute(
            "INSERT OR IGNORE INTO report_links (url, title, index_page, discovered_at) "
            "VALUES (?, ?, ?, ?)",
            (link["url"], link["title"], link["index_page"], link["discovered_at"]),
        )
        if cur.rowcount:
            new_count += 1
    conn.commit()
    return new_count


def fetch_index(max_pages: int = 0, sleep: float = 1.0) -> int:
    db_path = get_db_path("links")
    total_new = 0

    with sqlite3.connect(db_path) as conn:
        page_num = 0
        while True:
            if page_num == 0:
                url = INDEX_FIRST
            else:
                url = INDEX_PAGE.format(n=page_num)

            print(f"[fetch_index] 抓取第 {page_num + 1} 页: {url}")
            html, resp_encoding, apparent_encoding = fetch_page(url)

            if html is None:
                print(f"[fetch_index] 页面不可访问，停止翻页")
                break

            links = parse_links(html, url)
            if not links:
                # 诊断输出
                soup_debug = BeautifulSoup(html, "html.parser")
                all_li = soup_debug.find_all("li")
                all_a = soup_debug.find_all("a", href=True)
                print(f"[fetch_index] 第 {page_num + 1} 页无有效链接，停止翻页")
                print(f"[fetch_index] DEBUG: HTML长度={len(html)}, <li>数量={len(all_li)}, <a>数量={len(all_a)}")
                print(f"[fetch_index] DEBUG: HTTP encoding={resp_encoding}, apparent={apparent_encoding}")
                # 打印前5个<a>的href
                for a in all_a[:5]:
                    print(f"[fetch_index] DEBUG:   <a href={a.get('href','')!r}> {a.get_text(strip=True)[:40]!r}")
                # 打印第一个 news_title li 的原始内容
                for li in soup_debug.find_all("li", class_="news_title")[:3]:
                    print(f"[fetch_index] DEBUG li内容: {str(li)[:300]!r}")
                # 打印页面中所有 <script src=...>，找数据加载 URL
                for s in soup_debug.find_all("script", src=True):
                    print(f"[fetch_index] DEBUG script src: {s.get('src')}")
                # 把完整HTML保存到文件方便检查
                debug_path = Path(__file__).resolve().parent.parent / "data" / "debug_index.html"
                debug_path.write_text(html, encoding="utf-8")
                print(f"[fetch_index] DEBUG: 完整HTML已保存到 {debug_path}")
                break

            new = insert_links(conn, links)
            total_new += new
            print(f"[fetch_index]   发现 {len(links)} 条链接，新增 {new} 条")

            page_num += 1
            if max_pages and page_num >= max_pages:
                print(f"[fetch_index] 已达到最大页数限制 {max_pages}，停止")
                break

            time.sleep(sleep)

    print(f"[fetch_index] 完成，共新增 {total_new} 条链接")
    return total_new


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=0, help="最多抓取的页数，0=不限制")
    parser.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()

    fetch_index(max_pages=args.max_pages, sleep=args.sleep)
