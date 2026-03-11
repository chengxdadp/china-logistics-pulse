"""
公共工具函数
"""
import re
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def get_db_path(name: str) -> Path:
    """返回 data 目录下的数据库路径"""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"{name}.db"


def normalize_number(text: str) -> str:
    """全角数字转半角，移除多余空格"""
    full_to_half = str.maketrans(
        "０１２３４５６７８９．，",
        "0123456789.,",
    )
    return text.translate(full_to_half).strip()


def parse_date_range(title: str, publish_date: datetime.date):
    """
    从通报标题解析起止日期，结合发布日期确定年份。

    标题格式：
      - "3月2日—3月8日全国物流保通保畅运行情况"
      - "2025年12月29日—2026年1月4日全国物流保通保畅运行情况"（跨年，带年份）

    返回 (week_start, week_end) datetime.date 对象，或 (None, None)。
    """
    # 尝试匹配带年份的跨年格式：YYYY年M月D日—YYYY年M月D日
    pattern_year = re.compile(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日[—\-]+(\d{4})年(\d{1,2})月(\d{1,2})日"
    )
    m = pattern_year.search(title)
    if m:
        y1, mo1, d1, y2, mo2, d2 = (int(x) for x in m.groups())
        return datetime.date(y1, mo1, d1), datetime.date(y2, mo2, d2)

    # 普通格式：M月D日—M月D日
    pattern_simple = re.compile(
        r"(\d{1,2})月(\d{1,2})日[—\-]+(\d{1,2})月(\d{1,2})日"
    )
    m = pattern_simple.search(title)
    if not m:
        # 兜底：单日格式 "M月D日全国物流..." 或 "YYYY年M月D日全国物流..."
        pattern_single_year = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
        ms = pattern_single_year.search(title)
        if ms:
            y, mo, d = int(ms.group(1)), int(ms.group(2)), int(ms.group(3))
            try:
                day = datetime.date(y, mo, d)
                return day, day
            except ValueError:
                pass
        pattern_single = re.compile(r"(\d{1,2})月(\d{1,2})日")
        ms = pattern_single.search(title)
        if ms:
            mo, d = int(ms.group(1)), int(ms.group(2))
            try:
                day = datetime.date(publish_date.year, mo, d)
                # 单日比发布日期晚超30天则取上一年
                if (day - publish_date).days > 30:
                    day = datetime.date(publish_date.year - 1, mo, d)
                return day, day
            except ValueError:
                pass
        return None, None

    mo1, d1, mo2, d2 = (int(x) for x in m.groups())
    pub_year = publish_date.year

    # 用发布年份构建候选日期
    try:
        # 跨年情况：如 12月X日—1月X日，起始月份大于结束月份
        if mo1 > mo2:
            # 结束日期在发布年份，起始日期在前一年
            start = datetime.date(pub_year - 1, mo1, d1)
            end = datetime.date(pub_year, mo2, d2)
        else:
            start = datetime.date(pub_year, mo1, d1)
            end = datetime.date(pub_year, mo2, d2)
            # 如果结束日期比发布日期晚超过 30 天，可能跨年
            if (end - publish_date).days > 30:
                start = datetime.date(pub_year - 1, mo1, d1)
                end = datetime.date(pub_year - 1, mo2, d2)
    except ValueError:
        return None, None

    return start, end


def calc_iso_week(date: datetime.date) -> tuple[int, int]:
    """返回 (iso_year, iso_week)"""
    iso = date.isocalendar()
    return iso[0], iso[1]


def setup_chinese_font():
    """
    配置 matplotlib 中文字体。
    找不到中文字体时降级为英文标签，返回 True 表示支持中文。
    """
    import matplotlib
    import matplotlib.pyplot as plt

    chinese_fonts = [
        "Source Han Sans CN",
        "Noto Sans CJK SC",
        "SimHei",
        "Microsoft YaHei",
        "WenQuanYi Micro Hei",
        "PingFang SC",
        "STHeiti",
    ]

    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}

    for font in chinese_fonts:
        if font in available:
            matplotlib.rcParams["font.family"] = font
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True

    # 降级：使用系统默认，禁用中文
    matplotlib.rcParams["axes.unicode_minus"] = False
    return False
