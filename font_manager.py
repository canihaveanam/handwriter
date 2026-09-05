import os
import hashlib

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class FontManager:
    def __init__(self, resource_path_func, fonts_dir="fonts", default_font="StyleA"):
        self.resource_path_func = resource_path_func
        self.fonts_dir = fonts_dir
        self.default_font = default_font

        # 已经成功注册到 ReportLab 的字体
        # 格式：
        # {
        #     "StyleA": "HWFont_xxxxxxxxxxxx"
        # }
        self.registered_fonts = {}

    def get_fonts_dir(self):
        """获取 fonts 目录真实路径"""
        return self.resource_path_func(self.fonts_dir)

    def list_fonts(self):
        """
        扫描 fonts 文件夹。

        返回：
        [
            "StyleA",
            "StyleB",
            "StyleC"
        ]
        """
        fonts_dir = self.get_fonts_dir()

        if not os.path.isdir(fonts_dir):
            return []

        fonts = []

        for filename in os.listdir(fonts_dir):
            if filename.lower().endswith(".ttf"):
                font_name = os.path.splitext(filename)[0]
                fonts.append(font_name)

        # 保证下拉框顺序稳定
        fonts.sort(key=str.lower)

        return fonts

    def get_default_font(self):
        """
        获取默认字体。
        优先 StyleA。
        如果 StyleA 不存在，则使用 fonts 中第一个字体。
        """
        fonts = self.list_fonts()

        if self.default_font in fonts:
            return self.default_font

        if fonts:
            return fonts[0]

        return None

    def get_font_path(self, font_name):
        """
        根据字体名称获取真实字体路径。

        注意：
        不直接相信用户传来的文件路径，
        只允许使用 fonts 文件夹中实际存在的字体。
        """
        available_fonts = self.list_fonts()

        if font_name not in available_fonts:
            return None

        filename = font_name + ".ttf"

        return os.path.join(
            self.get_fonts_dir(),
            filename
        )

    def _make_reportlab_font_name(self, font_name):
        """
        给 ReportLab 创建内部字体名称。

        不直接使用文件名作为 ReportLab 字体名，
        避免以后中文字体名、空格、特殊字符带来问题。
        """
        digest = hashlib.sha1(
            font_name.encode("utf-8")
        ).hexdigest()[:12]

        return f"HWFont_{digest}"

    def register_font(self, font_name):
        """
        注册指定字体。

        成功返回 ReportLab 内部字体名称。
        失败返回 None。
        """

        # 已经注册过就不重复注册
        if font_name in self.registered_fonts:
            return self.registered_fonts[font_name]

        font_path = self.get_font_path(font_name)

        if not font_path:
            return None

        if not os.path.isfile(font_path):
            return None

        reportlab_font_name = self._make_reportlab_font_name(
            font_name
        )

        try:
            pdfmetrics.registerFont(
                TTFont(
                    reportlab_font_name,
                    font_path
                )
            )

            self.registered_fonts[font_name] = reportlab_font_name

            return reportlab_font_name

        except Exception as e:
            print(
                f"字体注册失败: {font_name}, "
                f"路径: {font_path}, "
                f"错误: {e}",
                flush=True
            )

            return None

    def get_reportlab_font_name(self, font_name=None):
        """
        获取最终用于生成 PDF 的 ReportLab 字体名称。

        流程：
        用户指定字体
            ↓
        指定字体不存在
            ↓
        默认字体
            ↓
        默认字体也失败
            ↓
        Helvetica
        """

        available_fonts = self.list_fonts()

        # 用户没有传字体，或者传了不存在的字体
        if not font_name or font_name not in available_fonts:
            font_name = self.get_default_font()

        if font_name:
            registered_name = self.register_font(font_name)

            if registered_name:
                return registered_name

        # 最后的保险
        return "Helvetica"