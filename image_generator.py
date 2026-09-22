from PIL import Image, ImageDraw, ImageFont
import math
import random


class ImageGenerator:

    def __init__(
        self,
        font_manager,
        background_image
    ):
        self.font_manager = font_manager
        self.background_image = background_image

    # =========================================================
    # 字体
    # =========================================================

    def get_pillow_font(
        self,
        font_name=None,
        font_size=40
    ):
        available_fonts = (
            self.font_manager.list_fonts()
        )

        if (
            not font_name
            or font_name not in available_fonts
        ):
            font_name = (
                self.font_manager
                .get_default_font()
            )

        if not font_name:
            raise RuntimeError(
                "fonts 文件夹中没有可用字体"
            )

        font_path = (
            self.font_manager
            .get_font_path(font_name)
        )

        if not font_path:
            raise RuntimeError(
                f"找不到字体文件: {font_name}"
            )

        return ImageFont.truetype(
            font_path,
            max(
                1,
                int(round(font_size))
            )
        )

    # =========================================================
    # 文字宽度
    # =========================================================

    def measure_char_width(
        self,
        draw,
        ch,
        font
    ):
        if not ch:
            return 0

        try:
            return draw.textlength(
                ch,
                font=font
            )

        except AttributeError:
            bbox = draw.textbbox(
                (0, 0),
                ch,
                font=font
            )

            return (
                bbox[2]
                - bbox[0]
            )

    def measure_text_width(
        self,
        draw,
        text,
        font,
        letter_spacing=0
    ):
        if not text:
            return 0

        text = str(text)

        total = 0.0

        for index, ch in enumerate(text):

            total += (
                self.measure_char_width(
                    draw,
                    ch,
                    font
                )
            )

            if index < len(text) - 1:
                total += (
                    letter_spacing
                )

        return total

    # =========================================================
    # 中文自动换行
    # =========================================================

    def wrap_text(
        self,
        draw,
        text,
        font,
        max_width,
        letter_spacing=0
    ):
        """
        按正文框宽度自动换行。

        支持：
        - 用户主动换行
        - 空行
        - 字距
        - 中文标点避免不合理地出现在新行开头
        """

        no_line_start = (
            "，。！？：；、"
            "）》】」』"
            "”’"
            "…"
            ",.!?:;"
        )

        result_lines = []

        max_width = max(
            1.0,
            float(max_width)
        )

        paragraphs = str(text).split(
            "\n"
        )

        for paragraph in paragraphs:

            if paragraph == "":
                result_lines.append("")
                continue

            current_line = ""

            for ch in paragraph:

                test_line = (
                    current_line
                    + ch
                )

                test_width = (
                    self.measure_text_width(
                        draw=draw,
                        text=test_line,
                        font=font,
                        letter_spacing=
                            letter_spacing
                    )
                )

                if test_width <= max_width:
                    current_line = test_line
                    continue

                if current_line:

                    if ch in no_line_start:

                        current_line += ch

                        result_lines.append(
                            current_line
                        )

                        current_line = ""

                    else:

                        result_lines.append(
                            current_line
                        )

                        current_line = ch

                else:

                    result_lines.append(ch)

                    current_line = ""

            if current_line:
                result_lines.append(
                    current_line
                )

        return result_lines

    # =========================================================
    # 分页
    # =========================================================

    def paginate_lines(
        self,
        lines,
        body_height,
        line_height
    ):
        """
        根据正文框高度把排版后的行切成多页。

        每一页继续使用完全相同的正文框：
        x / y / width / height 都不变。
        """

        body_height = float(
            body_height
        )

        line_height = float(
            line_height
        )

        if line_height <= 0:
            raise ValueError(
                "行距必须大于 0"
            )

        lines_per_page = int(
            math.floor(
                body_height
                / line_height
            )
        )

        if lines_per_page < 1:
            raise ValueError(
                "正文框高度太小，至少要能放下一行文字"
            )

        if not lines:
            return [[]]

        pages = []

        for start in range(
            0,
            len(lines),
            lines_per_page
        ):

            pages.append(
                lines[
                    start:
                    start + lines_per_page
                ]
            )

        return pages

    # =========================================================
    # 逐字绘制一行
    # =========================================================

    def draw_text_line(
        self,
        draw,
        text,
        font,
        y,
        max_width,
        letter_spacing=0,
        char_jitter=0
    ):
        jitter_margin = max(
            0.0,
            float(char_jitter)
        )

        current_x = jitter_margin

        usable_width = max(
            1.0,
            float(max_width)
            - jitter_margin * 2
        )

        for ch in str(text):

            char_width = (
                self.measure_char_width(
                    draw,
                    ch,
                    font
                )
            )

            if char_jitter:

                draw_x = (
                    current_x
                    + random.uniform(
                        -char_jitter,
                        char_jitter
                    )
                )

            else:

                draw_x = current_x

            draw.text(
                (
                    draw_x,
                    y
                ),
                ch,
                font=font,
                fill=(
                    0,
                    0,
                    0,
                    255
                )
            )

            current_x += (
                char_width
                + letter_spacing
            )

            if current_x > usable_width:
                break

    # =========================================================
    # 单行字段框
    # =========================================================

    def draw_single_line_box(
        self,
        width,
        height,
        text,
        font,
        letter_spacing=0,
        char_jitter=0
    ):
        width = max(
            1,
            int(round(width))
        )

        height = max(
            1,
            int(round(height))
        )

        layer = Image.new(
            "RGBA",
            (
                width,
                height
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        draw = ImageDraw.Draw(
            layer
        )

        self.draw_text_line(
            draw=draw,
            text=str(text),
            font=font,
            y=0,
            max_width=width,
            letter_spacing=
                letter_spacing,
            char_jitter=
                char_jitter
        )

        return layer

    # =========================================================
    # 一页正文
    # =========================================================

    def draw_body_lines(
        self,
        width,
        height,
        lines,
        font,
        line_height,
        letter_spacing=0,
        char_jitter=0,
        line_jitter=0
    ):
        width = max(
            1,
            int(round(width))
        )

        height = max(
            1,
            int(round(height))
        )

        line_height = max(
            1.0,
            float(line_height)
        )

        letter_spacing = float(
            letter_spacing
        )

        char_jitter = max(
            0.0,
            float(char_jitter)
        )

        line_jitter = max(
            0.0,
            float(line_jitter)
        )

        layer = Image.new(
            "RGBA",
            (
                width,
                height
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        draw = ImageDraw.Draw(
            layer
        )

        current_y = 0.0

        for line in lines:

            if (
                current_y
                + line_height
                > height
            ):
                break

            if line == "":

                current_y += (
                    line_height
                )

                continue

            if line_jitter:

                draw_y = (
                    current_y
                    + random.uniform(
                        -line_jitter,
                        line_jitter
                    )
                )

                draw_y = max(
                    0.0,
                    min(
                        draw_y,
                        max(
                            0.0,
                            height
                            - line_height
                        )
                    )
                )

            else:

                draw_y = current_y

            self.draw_text_line(
                draw=draw,
                text=line,
                font=font,
                y=draw_y,
                max_width=width,
                letter_spacing=
                    letter_spacing,
                char_jitter=
                    char_jitter
            )

            current_y += (
                line_height
            )

        return layer

    # =========================================================
    # 在一张画布上绘制 4 个字段
    # =========================================================

    def draw_fields_on_page(
        self,
        image,
        fields,
        boxes,
        font,
        letter_spacing,
        char_jitter
    ):
        for field_name in [
            "病区",
            "姓名",
            "床号",
            "住院号"
        ]:

            box = boxes.get(
                field_name
            )

            if not box:
                continue

            value = fields.get(
                field_name,
                ""
            )

            layer = (
                self.draw_single_line_box(
                    width=box.get(
                        "width",
                        1
                    ),
                    height=box.get(
                        "height",
                        1
                    ),
                    text=value,
                    font=font,
                    letter_spacing=
                        letter_spacing,
                    char_jitter=
                        char_jitter
                )
            )

            image.alpha_composite(
                layer,
                (
                    int(
                        round(
                            box.get(
                                "x",
                                0
                            )
                        )
                    ),
                    int(
                        round(
                            box.get(
                                "y",
                                0
                            )
                        )
                    )
                )
            )

    # =========================================================
    # 生成多页图片
    # =========================================================

    def create_images(
        self,
        text,
        fields,
        boxes,
        settings
    ):
        """
        返回：
            [PIL.Image, PIL.Image, ...]

        第1、2、3...页全部：
        - 使用同一个 base.jpg
        - 使用同一组 5 个框
        - 重复绘制病区/姓名/床号/住院号
        - 正文从上一页剩余内容继续
        """

        font_name = (
            settings.get(
                "font"
            )
        )

        font_size = (
            settings.get(
                "font_size",
                40
            )
        )

        line_height = (
            settings.get(
                "line_height",
                font_size * 1.5
            )
        )

        letter_spacing = (
            settings.get(
                "letter_spacing",
                0
            )
        )

        char_jitter = (
            settings.get(
                "char_jitter",
                0
            )
        )

        line_jitter = (
            settings.get(
                "line_jitter",
                0
            )
        )

        font = self.get_pillow_font(
            font_name,
            font_size
        )

        body_box = boxes.get(
            "正文"
        )

        if not body_box:
            raise ValueError(
                "缺少正文框"
            )

        body_width = float(
            body_box.get(
                "width",
                1
            )
        )

        body_height = float(
            body_box.get(
                "height",
                1
            )
        )

        # 用临时绘图对象计算文字宽度
        measure_image = Image.new(
            "RGBA",
            (
                max(
                    1,
                    int(round(body_width))
                ),
                100
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        measure_draw = ImageDraw.Draw(
            measure_image
        )

        wrap_width = max(
            1.0,
            body_width
            - float(char_jitter) * 2
        )

        lines = self.wrap_text(
            draw=measure_draw,
            text=text,
            font=font,
            max_width=
                wrap_width,
            letter_spacing=
                letter_spacing
        )

        page_lines = (
            self.paginate_lines(
                lines=lines,
                body_height=
                    body_height,
                line_height=
                    line_height
            )
        )

        images = []

        for lines_for_page in page_lines:

            image = Image.open(
                self.background_image
            ).convert(
                "RGBA"
            )

            # 每一页都按照同样的字段框重复绘制
            self.draw_fields_on_page(
                image=image,
                fields=fields,
                boxes=boxes,
                font=font,
                letter_spacing=
                    letter_spacing,
                char_jitter=
                    char_jitter
            )

            body_layer = (
                self.draw_body_lines(
                    width=
                        body_box.get(
                            "width",
                            1
                        ),
                    height=
                        body_box.get(
                            "height",
                            1
                        ),
                    lines=
                        lines_for_page,
                    font=font,
                    line_height=
                        line_height,
                    letter_spacing=
                        letter_spacing,
                    char_jitter=
                        char_jitter,
                    line_jitter=
                        line_jitter
                )
            )

            image.alpha_composite(
                body_layer,
                (
                    int(
                        round(
                            body_box.get(
                                "x",
                                0
                            )
                        )
                    ),
                    int(
                        round(
                            body_box.get(
                                "y",
                                0
                            )
                        )
                    )
                )
            )

            images.append(
                image.convert(
                    "RGB"
                )
            )

        return images

    # 兼容旧的阶段3/4调用：
    # 如果还有地方调用 create_image_preview，
    # 就返回多页中的第一页。
    def create_image_preview(
        self,
        text,
        fields,
        boxes,
        settings
    ):
        images = self.create_images(
            text=text,
            fields=fields,
            boxes=boxes,
            settings=settings
        )

        return images[0]
