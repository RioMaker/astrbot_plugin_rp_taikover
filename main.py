import asyncio
import json
import random
import tempfile
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from astrbot.api.event.filter import (
    EventMessageType,
    PermissionType,
    PlatformAdapterType,
)
import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import At

# 修复导入冲突：PIL的Image重命名为PILImage
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "luck_records_advanced.db")

# 创建UTC+8时区对象
china_tz = timezone(timedelta(hours=8))
INTRO_INFO = [
                "小咚祈祷中...",
                "小咔祈祷中...",
                "通关祈祷中...",
                "全连祈祷中...",
                "全良祈祷中...",
                "#&*D祈祷中...",
                "全可祈祷中...",
                "全连祈祷中...希望这次不掉...",
                "超级combo祈祷中...别断了...",
                "极限打击祈祷中...不掉音符...",
                "满分之梦祈祷中...求个好运气...",
                "极限挑战祈祷中...求不手抖...",
                "击鼓神力祈祷中...手速能跟上吗...",
                "节奏神降祈祷中...这次一定要过...",
                "音符全中祈祷中...求个完美结局...",
                "秒杀全图祈祷中...这一波能不能过...",
                "太鼓之魂祈祷中...请给我好运...",
                "全良祈祷中...请不要失误...",
                "不掉一分祈祷中...让所有音符都听话...",
                "全能挑战祈祷中...这次必须拿S...",
                "无敌节奏祈祷中...希望没有任何失误...",
                "完美击打祈祷中...加油，别掉了...",
                "极限连击祈祷中...这次不再丢分...",
                "连环打击祈祷中...希望手速能跟上...",
                "音符流畅祈祷中...求个完美音符...",
                "无误差祈祷中...手速和节奏齐飞...",
                "鼓声低语中...命运的回响已起...",
                "音符呢喃中...时光与节奏交织...",
                "古神祝福中...每一击皆为永恒...",
                "节奏涌动中...无尽的波动在召唤...",
                "灵魂共振中...节奏与我同在...",
                "无声的祈祷中...那道光将引领前行...",
                "沉寂低语中...鼓动将划破虚空...",
                "回响之力中...愿音符赐予力量...",
                "黑暗涌动中...节奏的引力将至...",
                "远古旋律中...音符注定归于命运...",
                "时间冻结中...每一次鼓击都为启示...",
                "古老旋律响起中...灵魂与节奏共鸣...",
                "天启低语中...鼓声是破晓的号角...",
                "无尽回声中...音符定将指引道路...",
                "寂静召唤中...节奏是永恒的序章...",
                "虚无低语中...每个音符是通往未知的钥匙...",
                "命运低语中...音符与节奏交织成网...",
                "神秘低语中...鼓声是古老力量的复苏...",
                "黑暗祝福中...音符的回响带来永恒的誓言...",
                "永恒低语中...节奏之力是无尽的庇佑..."
             ]
FORTUNE_TEXTS = ["大吉", "小吉", "吉", "末吉", "凶", "大凶"]
COLORS = [
    "红色",
    "蓝色",
    "绿色",
    "紫色",
    "白色",
    "黑色",
    "灰色",
    "粉色",
    "金色",
    "黄色",
    "橙色",
    "青色",
    "银色",
    "棕色",
    "透明色",
    "彩虹色",
    "铁锈色",
    "铜绿色",
    "靛蓝色",
    "翠绿色",
    "橄榄色",
    "茶色",
    "杏色",
    "铅灰色",
    "赤色",
    "雨色",
    "雪色",
    "霞色",
    "霜色",
    "霁色",
    "霰色",
    "霓色",
    "霪色",
    "霭色",
    "露色",
    "霹雳色",
    "霾色",
    "靥色",
    "青莲色",
    "青缥色",
    "青白色",
    "五彩斑斓的黑色",
    "五彩斑斓的白色",
    "五彩斑斓的透明色",
]
ADVICE_DO = [
    "出门逛街",
    "加班学习",
    "打扫卫生",
    "看书充电",
    "给喜欢的人表白",
    "搞副业",
    "出门逛街时顺便去游戏厅打太鼓达人",
    "加班学习后用太鼓达人来放松一下",
    "打扫卫生完毕后再来一曲太鼓达人减压",
    "看书充电之余练习太鼓达人提高节奏感",
    "给喜欢的人表白前一起玩太鼓达人增进感情",
    "搞副业的间隙打打太鼓达人激发灵感",
    "考段",
    "越级",
]
ADVICE_DONT = [
    "熬夜",
    "和人吵架",
    "冲动消费",
    "吃太多甜食",
    "迟到",
    "赖床",
    "深夜不戴耳机在家猛敲太鼓达人扰民",
    "为冲高分通宵达旦地敲太鼓达人损害身体",
    "在公共场所外放音量狂热打太鼓达人",
    "为攒金币砸钱抽太鼓达人周边买到吃土",
    "沉迷太鼓达人导致工作或学习荒废",
    "刚练手就直接开高难度谱面伤鼓又伤心",
    "考段",
    "越级",
    "熬夜打太鼓达人",
]
SCORE_NONE_INDEX = ["none-ji","none-ji-shine", "none-baicui","none-fenya"]

def init_db():
    """
    初始化数据库，如果 luck_records 和 luck_steals 表不存在，则创建。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 主表：存储每日运势
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS luck_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,        -- YYYY-MM-DD
            luck_value INTEGER NOT NULL,
            fortune_text TEXT NOT NULL,  -- 吉凶签
            color TEXT NOT NULL,         -- 幸运色
            advice_do TEXT NOT NULL,     -- 今日宜
            advice_dont TEXT NOT NULL    -- 今日忌
        )
    """
    )
    # 记录偷取运势事件，防止一天多次偷
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS luck_steals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stealer_id TEXT NOT NULL,   -- 偷运势的人
            target_id TEXT NOT NULL,    -- 被偷的人
            date TEXT NOT NULL          -- YYYY-MM-DD
        )
    """
    )
    conn.commit()
    conn.close()

def get_today_record(user_id: str):
    """
    获取用户今日的运势记录 (如果有)，返回一行(dict形式或tuple)。
    如果没有记录，返回 None。
    """
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, luck_value, fortune_text, color, advice_do, advice_dont 
        FROM luck_records
        WHERE user_id = ? AND date = ?
    """,
        (user_id, today_str),
    )
    row = c.fetchone()
    conn.close()
    if row:
        # row: (id, luck_value, fortune, color, do, dont)
        return {
            "id": row[0],
            "luck_value": row[1],
            "fortune_text": row[2],
            "color": row[3],
            "advice_do": row[4],
            "advice_dont": row[5],
        }
    return None

def create_today_record(user_id: str):
    """
    为用户在当天创建一条新的运势记录，并返回生成的数据。
    """
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    luck_value = random.randint(0, 100)
    fortune_text = random.choice(FORTUNE_TEXTS)
    color = random.choice(COLORS)
    advice_do_str = random.choice(ADVICE_DO)
    advice_dont_str = random.choice(ADVICE_DONT)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO luck_records (user_id, date, luck_value, fortune_text, color, advice_do, advice_dont)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            today_str,
            luck_value,
            fortune_text,
            color,
            advice_do_str,
            advice_dont_str,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "id":user_id,
        "luck_value": luck_value,
        "fortune_text": fortune_text,
        "color": color,
        "advice_do": advice_do_str,
        "advice_dont": advice_dont_str,
    }

def get_all_luck_records(user_id: str):
    """
    获取该用户全部的运势记录，按日期降序。
    返回列表：[(date, luck_value, fortune_text, color, advice_do, advice_dont), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT date, luck_value, fortune_text, color, advice_do, advice_dont
        FROM luck_records
        WHERE user_id = ?
        ORDER BY date DESC
    """,
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def delete_today_luck(user_id: str) -> bool:
    """
    删除用户当天的运势记录。返回 True 表示删除成功，False 表示无记录。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    c.execute(
        """
        DELETE FROM luck_records
        WHERE user_id = ? AND date = ?
    """,
        (user_id, today_str),
    )
    rowcount = c.rowcount
    conn.commit()
    conn.close()
    return rowcount > 0


def delete_all_luck(user_id: str) -> int:
    """
    删除用户所有运势记录，返回删除的条数。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        DELETE FROM luck_records
        WHERE user_id = ?
    """,
        (user_id,),
    )
    rowcount = c.rowcount
    conn.commit()
    conn.close()
    return rowcount


def get_today_rank():
    """
    获取今天所有人的运势，按 luck_value DESC 排序。
    返回列表 [ (user_id, luck_value, fortune_text, color, advice_do, advice_dont), ...]
    """
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, luck_value, fortune_text, color, advice_do, advice_dont
        FROM luck_records
        WHERE date = ?
        ORDER BY luck_value DESC
    """,
        (today_str,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def has_stolen_today(stealer_id: str):
    """
    检查偷运势表中，stealer_id 今日是否已经偷过。
    """
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT 1 FROM luck_steals
        WHERE stealer_id = ? AND date = ?
    """,
        (stealer_id, today_str),
    )
    row = c.fetchone()
    conn.close()
    return row is not None


def record_steal(stealer_id: str, target_id: str):
    """
    在 luck_steals 表中记录一条偷运势行为。
    """
    today_str = datetime.now(china_tz).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO luck_steals (stealer_id, target_id, date)
        VALUES (?, ?, ?)
    """,
        (stealer_id, target_id, today_str),
    )
    conn.commit()
    conn.close()


def update_luck_value(user_id: str, date_str: str, new_value: int):
    """
    更新 luck_records 表中某条记录的运势值（仅限当日），注意需要保证不超过范围 [0, 100]。
    """
    if new_value < 0:
        new_value = 0
    if new_value > 100:
        new_value = 100
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        UPDATE luck_records
        SET luck_value = ?
        WHERE user_id = ? AND date = ?
    """,
        (new_value, user_id, date_str),
    )
    conn.commit()
    conn.close()


@register("taiko_rp", "Rio", "测一下taiko人品", "0.3")
class taikoRP(Star):
    CANVAS_WIDTH = 800  # 画布宽度
    CANVAS_HEIGHT = 800  # 画布高度
    AVATAR_SIZE = 280  # 头像大小
    SPACING_AVATAR_NAME = 20  # 头像与名称间距
    SPACING_NAME_DESC = 25  # 名称与描述间距
    SPACING_DESC_ANALYSIS = 30  # 描述与解析间距
    DESC_FONT_SIZE = 32  # 描述字体大小
    ANALYSIS_FONT_SIZE = 28  # 解析字体大小
    ANALYSIS_LINE_HEIGHT_FACTOR = 1.6  # 解析行高因子
    ANALYSIS_WIDTH_RATIO = 0.85  # 解析宽度比例
    NAME_FONT_SIZE = 66  # 名称字体大小
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        logger.debug(self.config)

        # 配置项
        self.admins_id: list[str] = context.get_config().get("admins_id", [])
        self.CANVAS_WIDTH = self.config.get("CANVAS_WIDTH", 800)  # 画布宽度
        self.CANVAS_HEIGHT = self.config.get("CANVAS_HEIGHT", 800)  # 画布高度
        self.AVATAR_SIZE = self.config.get("AVATAR_SIZE", 280)  # 头像大小
        self.SPACING_AVATAR_NAME = self.config.get("SPACING_AVATAR_NAME", 20)  # 头像与名称间距
        self.SPACING_NAME_DESC = self.config.get("SPACING_NAME_DESC", 25)  # 名称与描述间距
        self.SPACING_DESC_ANALYSIS = self.config.get("SPACING_DESC_ANALYSIS", 30)  # 描述与解析间距
        self.DESC_FONT_SIZE = self.config.get("DESC_FONT_SIZE", 32)  # 描述字体大小
        self.ANALYSIS_FONT_SIZE = self.config.get("ANALYSIS_FONT_SIZE", 28)  # 解析字体大小
        self.ANALYSIS_LINE_HEIGHT_FACTOR = self.config.get("ANALYSIS_LINE_HEIGHT_FACTOR", 1.6) # 解析行高因子
        self.ANALYSIS_WIDTH_RATIO = self.config.get("ANALYSIS_WIDTH_RATIO", 0.85) # 解析宽度比例
        self.NAME_FONT_SIZE = self.config.get("NAME_FONT_SIZE", 66)  # 名称字体大小

        logger.debug(
            f"{self.CANVAS_WIDTH} \n"+
            f"{self.CANVAS_HEIGHT} \n"+
            f"{self.AVATAR_SIZE} \n"+
            f"{self.SPACING_AVATAR_NAME} \n"+
            f"{self.SPACING_NAME_DESC} \n"+
            f"{self.SPACING_DESC_ANALYSIS} \n"+
            f"{self.DESC_FONT_SIZE} \n"+
            f"{self.ANALYSIS_FONT_SIZE} \n"+
            f"{self.ANALYSIS_LINE_HEIGHT_FACTOR} \n"+
            f"{self.ANALYSIS_WIDTH_RATIO} \n"+
            f"{self.NAME_FONT_SIZE} \n"
        )
        
        # 初始化路径
        self.plugin_dir = Path(__file__).parent
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_rollpig")
        self.res_dir = self.plugin_dir / "resource"
        self.font_dir = self.res_dir / "font"  # 插件内字体目录（跨平台优先）
        self.piginfo_path = self.res_dir / "score.json"
        self.image_dir = self.res_dir / "image"

        # 初始化数据
        self.pig_list = self.load_json(self.piginfo_path, [])
        if not self.pig_list:
            logger.error("小猪信息为空或不存在，请检查资源文件！")
        # self.today_path = self.plugin_data_dir / "rollpig_today.json"

        # 创建必要目录（自动创建font文件夹）
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.font_dir.mkdir(parents=True, exist_ok=True)

        # 初始化字体（优先插件内自定义字体，跨平台兼容）
        self.font_regular = self._init_regular_font()  # 常规字体（描述/解析）
        self.font_bold = self._init_bold_font()  # 加粗字体（名称）

    def _load_font(
        self, font_candidates: list[str | Path], size: int, purpose: str
    ) -> ImageFont.FreeTypeFont | None:
        """
        通用字体加载器，按候选顺序加载可用字体\n
        :param font_candidates: 字体路径候选列表
        :param size: 字体大小
        :param purpose: 字体用途描述
        :return: 加载的字体对象，失败则返回默认字体
        """
        for font_path in font_candidates:
            if Path(font_path).exists():
                try:
                    return ImageFont.truetype(str(font_path), size)
                except Exception as e:
                    logger.warning(f"加载{purpose}字体{font_path}失败：{e}")
                    continue
        logger.warning(f"未找到{purpose}字体，使用默认字体")
        return ImageFont.load_default()

    def _init_regular_font(self) -> ImageFont.FreeTypeFont | None:
        """初始化常规字体（可爱字体，用于描述/解析）"""
        font_paths = [
            self.font_dir / "可爱字体.ttf",
            self.font_dir / "SourceHanSansCN-Regular.otf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        return self._load_font(font_paths, self.DESC_FONT_SIZE, "常规")

    def _init_bold_font(self) -> ImageFont.FreeTypeFont | None:
        """初始化加粗字体（荆南麦圆体，用于名称）"""
        font_paths = [
            self.font_dir / "荆南麦圆体.otf",
            self.font_dir / "SourceHanSansCN-Bold.otf",
            "C:/Windows/Fonts/msyhbd.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        return self._load_font(font_paths, self.NAME_FONT_SIZE, "加粗")

    def _get_text_size(
        self, text: str, font: ImageFont.FreeTypeFont
    ) -> tuple[int, int]:
        """
        兼容PIL不同版本的文字尺寸计算\n
        :param text: 文字内容
        :param font: 字体对象
        :return: 文字宽高元组
        """
        draw = ImageDraw.Draw(PILImage.new("RGB", (1, 1)))
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except:
            return draw.textsize(text, font=font)

    def _draw_bold_text(
        self,
        draw: ImageDraw.ImageDraw,
        pos: tuple,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple,
    ):
        """
        模拟文字加粗（兜底方案）\n
        :param draw: ImageDraw对象
        :param pos: 文字位置
        :param text: 文字内容
        :param font: 字体对象
        :param fill: 文字颜色
        """
        x, y = pos
        offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for ox, oy in offsets:
            draw.text((x + ox, y + oy), text, fill=fill, font=font)
        draw.text((x, y), text, fill=fill, font=font)
   
    #   none use
    def load_json(self, path: Path, default):
        """
        加载JSON文件\n
        :param path: 文件路径
        :param default: 默认值（文件不存在或解析失败时使用）
        :return: 解析后的数据对象
        """
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return default
        try:
            return json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            logger.error(f"JSON文件解析失败，重置为默认值：{path}")
            path.write_text(
                json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return default
    #   none use    
    # def save_json(self, path: Path, data):
    #     """
    #     保存JSON数据\n
    #     :param path: 文件路径
    #     :param data: 数据对象
    #     """
    #     path.parent.mkdir(parents=True, exist_ok=True)
    #     path.write_text(
    #         json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    #     )

    def find_image_file(self, score_id: str) -> Path | None:
        """
        查找对应ID的图片文件\n
        :param score_id: 评价ID
        :return: 图片文件路径，未找到返回None
        """
        exts = ["png", "jpg", "jpeg", "webp", "gif"]
        for ext in exts:
            file = self.image_dir / f"{score_id}.{ext}"
            if file.exists():
                logger.debug(f"找到的评价文件：{file.absolute()}")
                return file
        logger.warning(f"未找到评价ID {score_id} 对应的图片文件")
        return None
    
    def render_rp_image(self, rp_data: dict) -> Path | None:
        """
        整体居中渲染（垂直+水平双居中）\n
        :param rp_data: rp数据字典
        :return: 生成的图片临时文件路径，失败返回None
        """
        # record_id=rp_data["id"]
        user_name = rp_data.get("user_name","???")
        record_luck_value = rp_data["luck_value"]
        record_fortune_text = rp_data["fortune_text"]
        record_color = rp_data["color"]
        record_advice_do = rp_data["advice_do"]
        record_advice_dont = rp_data["advice_dont"]
    
        none_score = random.choice(SCORE_NONE_INDEX)
        rp_id = rp_data.get("rp_id", none_score)
        rp_name = f"【今日RP值: {record_luck_value}】"
        rp_desc = (
                    f"Hi~ “{user_name}” \n"
                    f"今日签: {record_fortune_text} 幸运色: {record_color}"
                  )
        rp_analysis = (
                f'宜: {record_advice_do} \n'+
                f'忌: {record_advice_dont}'
        )

        # 1. 画布基础配置
        canvas_width = self.CANVAS_WIDTH
        canvas_height = self.CANVAS_HEIGHT
        canvas = PILImage.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # x.获取当前日期，格式化为YYYYMMDD
        current_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        LUP_TAG = f"Date:{current_date}"
        # x.2绘制日期文本（左上角）
        date_font = self.font_regular.font_variant(size=16)  # 设置较小的字体
        date_w, date_h = self._get_text_size(LUP_TAG, date_font)
        date_x = 10  # 离左边的距离
        date_y = 10  # 离上边的距离
        draw.text((date_x, date_y), current_date, fill=(0, 0, 0), font=date_font)

        # 2. 预加载所有元素并计算尺寸（用于总高度计算）
        # 2.1 头像尺寸【核心修改：放大到280x280】
        avatar_w, avatar_h = self.AVATAR_SIZE, self.AVATAR_SIZE
        avatar = None
        avatar_path = self.find_image_file(rp_id)
        if avatar_path:
            try:
                avatar = PILImage.open(avatar_path)
                avatar.resize((avatar_w, avatar_h))
                # 居中裁剪（保证正方形，适配新尺寸：280/2=140）
                if avatar.size != (avatar_w, avatar_h):
                    center_x = avatar.width // 2
                    center_y = avatar.height // 2
                    half = self.AVATAR_SIZE // 2
                    crop_box = (
                        center_x - half,
                        center_y - half,
                        center_x + half,
                        center_y + half,
                    )
                    avatar = avatar.crop(crop_box)
            except Exception as e:
                logger.error(f"加载rp图片失败：{str(e)}")
                avatar = None

        # 2.2 名称尺寸
        name_font = self.font_bold
        name_w, name_h = self._get_text_size(rp_name, name_font)

        # 2.3 描述尺寸
        desc_font = self.font_regular.font_variant(
            size=self.DESC_FONT_SIZE
        )  # 匹配示例的描述字号
        desc_w, desc_h = self._get_text_size(rp_desc, desc_font)

        # 2.4 解析尺寸（自动换行后）
        analysis_font = self.font_regular.font_variant(size=self.ANALYSIS_FONT_SIZE)
        line_height = int(
            self.ANALYSIS_FONT_SIZE * self.ANALYSIS_LINE_HEIGHT_FACTOR
        )  # 匹配示例的行间距
        max_analysis_width = int(
            canvas_width * self.ANALYSIS_WIDTH_RATIO
        )  # 更宽的解析区域
        # 解析文字换行
        analysis_lines = []
        current_line = ""
        for char in rp_analysis:
            current_line += char
            line_w, _ = self._get_text_size(current_line, analysis_font)
            if line_w > max_analysis_width:
                analysis_lines.append(current_line[:-1])
                current_line = char
        if current_line:
            analysis_lines.append(current_line)
        # 计算解析总高度
        analysis_total_h = len(analysis_lines) * line_height

        # 3. 计算整体内容总高度（所有元素+间距）
        spacing_avatar_name = (
            self.SPACING_AVATAR_NAME
        )  # 头像放大后，间距从30调小到20，避免布局拥挤
        spacing_name_desc = self.SPACING_NAME_DESC  # 名称到描述的间距保持
        spacing_desc_analysis = self.SPACING_DESC_ANALYSIS  # 描述到解析的间距保持
        total_content_h = (
            avatar_h
            + spacing_avatar_name
            + name_h
            + spacing_name_desc
            + desc_h
            + spacing_desc_analysis
            + analysis_total_h
        )

        # 4. 计算垂直居中的起始Y坐标（核心：让整个内容块在画布中垂直居中）
        start_y = (canvas_height - total_content_h) // 2

        # 5. 绘制所有元素（基于起始Y坐标，保证整体居中）
        # 5.1 绘制头像（水平+垂直居中）
        avatar_x = (canvas_width - avatar_w) // 2
        avatar_y = start_y
        if avatar:
            canvas.paste(
                avatar,
                (avatar_x, avatar_y),
                mask=avatar if avatar.mode == "RGBA" else None,
            )
        else:
            # 头像加载失败时的提示（适配新尺寸）
            error_font = self.font_regular.font_variant(size=24)
            error_text = "图片加载失败"
            error_w, error_h = self._get_text_size(error_text, error_font)
            error_x = (canvas_width - error_w) // 2
            draw.text(
                (error_x, avatar_y + 120),  # 从90调到120，适配280高度的头像居中
                error_text,
                fill=(255, 0, 0),
                font=error_font,
            )

        # 5.2 绘制名称（水平居中）
        name_y = avatar_y + avatar_h + spacing_avatar_name
        name_x = (canvas_width - name_w) // 2
        self._draw_bold_text(draw, (name_x, name_y), rp_name, name_font, (0, 0, 0))

        # 5.3 绘制描述（水平居中）
        desc_y = name_y + name_h + spacing_name_desc
        desc_x = (canvas_width - desc_w) // 2
        draw.text((desc_x, desc_y), rp_desc, fill=(85, 85, 85), font=desc_font)

        # 5.4 绘制解析（逐行水平居中）
        analysis_y = desc_y + desc_h + spacing_desc_analysis
        for line in analysis_lines:
            line_w, line_h = self._get_text_size(line, analysis_font)
            line_x = (canvas_width - line_w) // 2
            draw.text((line_x, analysis_y), line, fill=(51, 51, 51), font=analysis_font)
            analysis_y += line_height

        # 6. 保存临时文件
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                canvas.save(tmp_path, format="PNG", quality=95)
            logger.debug(f"合成图片成功，临时文件路径：{tmp_path.absolute()}")
            if not tmp_path.exists():
                logger.error(f"临时文件创建失败：{tmp_path}")
                return None
            return tmp_path
        except Exception as e:
            logger.error(f"合成图片失败：{str(e)}")
            return None

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("rp_init")
    async def rp_init(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        if user_id in self.admins_id:
            init_db()
            try:
                await event.send(event.plain_result("sqlite3 初始化成功！"))
            except Exception as e:
                await event.send(event.plain_result("sqlite3 初始化失败，请检查错误信息。"))
        else:
            await event.send(event.plain_result("无权限，请联系管理员。"))
        
    @filter.command("rp help",alias={'rp 帮助','rp HELP'})
    async def help(self, event: AstrMessageEvent,):
        help_text = (
                "【rp命令帮助】\n"
                "/rp               查看/生成今天的运势\n"
                # "/rp记录           查看你全部历史运势\n"
                # "/rp删除 today     删除今天运势\n"
                # "/rp删除 all       删除所有运势记录\n"
                # "/rp排行榜         今日运势排行榜\n"
                # "/rp偷 @某人       偷取对方运势(每日一次)\n"
                # "更多说明可自行扩展~"
            )
        await event.send(event.plain_result(help_text))
        event.stop_event() 

    @filter.command("rp")
    async def rp(self, event: AstrMessageEvent):
        """ 获取今日rp """ # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_id = event.get_sender_id()
        logger.info("user_id:"+user_id)
        record = get_today_record(user_id)
        if record is None:
                # 当天未抽，随机生成
                record = create_today_record(user_id)
        else:
            # 已有记录，直接返回
            record = record
        val_score_id = random.choice(SCORE_NONE_INDEX)
        if record['luck_value']>99:
            val_score_id = "ji"
        elif record['luck_value']>94:
            val_score_id = "ziya"
        elif record['luck_value']>89:
            val_score_id = "fenya"
        elif record['luck_value']>79:
            val_score_id = "jinya"
        elif record['luck_value']>69:
            val_score_id = "yincui"
        elif record['luck_value']>59:
            val_score_id = "tongcui"
        elif record['luck_value']>49:
            val_score_id = "baicui"
        else:
            val_score_id = random.choice(SCORE_NONE_INDEX)
        record["rp_id"]=val_score_id
        record["user_name"] = event.get_sender_name()
        
        await self.send_rendered_rp(event, record, user_id)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("rp_test")
    async def rp_cmd(self, event: AstrMessageEvent, rp_score:int):
        """ 管理员命令示例 """
        user_id = event.get_sender_id()
        if user_id in self.admins_id:
            await event.send(event.plain_result("管理员命令执行成功！"))
            """ 获取今日rp """ # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
            user_id = event.get_sender_id()
            logger.info("user_id:"+user_id)
            record = get_today_record(user_id)
            if record is None:
                    # 当天未抽，随机生成
                    record = create_today_record(user_id)
            else:
                # 已有记录，直接返回
                record = record
            record['luck_value'] = rp_score
            val_score_id = random.choice(SCORE_NONE_INDEX)
            if record['luck_value']>99:
                val_score_id = "ji"
            elif record['luck_value']>94:
                val_score_id = "ziya"
            elif record['luck_value']>89:
                val_score_id = "fenya"
            elif record['luck_value']>79:
                val_score_id = "jinya"
            elif record['luck_value']>69:
                val_score_id = "yincui"
            elif record['luck_value']>59:
                val_score_id = "tongcui"
            elif record['luck_value']>49:
                val_score_id = "baicui"
            else:
                val_score_id = random.choice(SCORE_NONE_INDEX)
            record["rp_id"]=val_score_id
            record["user_name"] = event.get_sender_name()
            
            await self.send_rendered_rp(event, record, user_id)
        else:
            await event.send(event.plain_result("无权限，请联系管理员。"))

    async def send_rendered_rp(
        self, event: AstrMessageEvent, rp_data: dict, user_id: str
    ):
        """合成并发送图片"""
        # 使用线程池异步执行CPU密集型任务
        img_path = await asyncio.to_thread(self.render_rp_image, rp_data)
        if img_path and img_path.exists():
            try:
                intro_info_str = random.choice(INTRO_INFO)
                # logger.info("1:"+intro_info_str)
                chain = [Comp.Plain(intro_info_str)]
                # logger.info("2")
                group_id = event.get_group_id()
                # logger.info("3-group:"+group_id)
                # logger.info("3-user:"+user_id)
                if group_id:
                    chain.insert(0, Comp.At(qq=user_id))
                # logger.info("4")
                await event.send(event.chain_result(chain))
                # logger.info("5")
                await event.send(event.image_result(str(img_path.absolute())))
                logger.info("合成图片发送成功")
                return
            except Exception as e:
                logger.error(f"发送合成图片失败：{str(e)}")
            finally:
                try:
                    img_path.unlink(missing_ok=True)
                except Exception as cleanup_err:
                    logger.warning(f"清理临时图片失败：{cleanup_err}")

        await self.send_fallback_msg(event, rp_data)

    async def send_fallback_msg(self, event: AstrMessageEvent, rp_data: dict):
        """降级发送：原始图片 + 纯文本"""
        none_score = random.choice(SCORE_NONE_INDEX)
        rp_id = rp_data.get("rp_id", none_score)
        val_score = "  "
        if rp_data['luck_value']>99:
            val_score = "極"
        elif rp_data['luck_value']>94:
            val_score = "紫雅"
        elif rp_data['luck_value']>89:
            val_score = "粉雅"
        elif rp_data['luck_value']>79:
            val_score = "金雅"
        elif rp_data['luck_value']>69:
            val_score = "银粋"
        elif rp_data['luck_value']>59:
            val_score = "铜粋"
        elif rp_data['luck_value']>49:
            val_score = "白粋"
        else:
            val_score = "  "
        text_msg = (
            # f"【今日rp】\n名称：{score_name}\n描述：{fortune_desc}\n解析：{rp_analysis}"
            f"【今日运势】\n"
            f"《{val_score}》\n"
            f"Hi~“ {event.get_sender_name()} ” \n"
            f"今日人品（RP）值：{rp_data['luck_value']}\n"
            f"今日签：{rp_data['fortune_text']}\n"
            f"幸运色：{rp_data['color']}\n"
            f"宜：{rp_data['advice_do']}；忌：{rp_data['advice_dont']}"
        )
        msg_chain = []

        avatar_path = self.find_image_file(rp_id)
        if avatar_path and avatar_path.exists():
            try:
                msg_chain.append(Comp.Image.fromFileSystem(str(avatar_path.absolute())))
            except Exception as e:
                logger.error(f"发送原始图片失败：{str(e)}")
                text_msg += "\n\n（图片发送失败，仅展示文字信息）"

        msg_chain.append(Comp.Plain(text_msg))
        await event.send(event.chain_result(msg_chain))

    async def terminate(self):
        """插件卸载清理"""
        logger.info("taiko_rp插件已卸载")