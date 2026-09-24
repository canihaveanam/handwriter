from PIL import Image, ImageDraw, ImageFont

import math
import random


class ImageGenerator:
    def __init__(self, font_manager, background_image):
        self.font_manager = font_manager
        self.background_image = background_image

    # =========================================================
    # 字体
    # =========================================================

    def get_pillow_font(self, font_name=None, font_size=40):
        available_fonts = self.font_manager.list_fonts()

        if not font_name or font_name not in available_fonts:
            font_name = self.font_manager.get_default_font()

        if not font_name:
            raise RuntimeError("fonts 文件夹中没有可用字体")

        font_path = self.font_manager.get_font_path(font_name)
        if not font_path:
            raise RuntimeError(f"找不到字体文件: {font_name}")

        return ImageFont.truetype(
            font_path,
            max(1, int(round(float(font_size)))),
        )

    # =========================================================
    # 文字宽度
    # =========================================================

    def measure_char_width(self, draw, ch, font):
        if not ch:
            return 0

        try:
            return draw.textlength(ch, font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), ch, font=font)
            return bbox[2] - bbox[0]

    def measure_text_width(self, draw, text, font, letter_spacing=0):
        if not text:
            return 0

        text = str(text)
        total = 0.0
        letter_spacing = float(letter_spacing)

        for index, ch in enumerate(text):
            total += self.measure_char_width(draw, ch, font)
            if index < len(text) - 1:
                total += letter_spacing

        return total

    # =========================================================
    # 中文自动换行
    # =========================================================

    def wrap_text(self, draw, text, font, max_width, letter_spacing=0):
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
        max_width = max(1.0, float(max_width))
        letter_spacing = float(letter_spacing)
        paragraphs = str(text).split("\n")

        for paragraph in paragraphs:
            if paragraph == "":
                result_lines.append("")
                continue

            current_line = ""

            for ch in paragraph:
                test_line = current_line + ch
                test_width = self.measure_text_width(
                    draw=draw,
                    text=test_line,
                    font=font,
                    letter_spacing=letter_spacing,
                )

                if test_width <= max_width:
                    current_line = test_line
                    continue

                if current_line:
                    if ch in no_line_start:
                        current_line += ch
                        result_lines.append(current_line)
                        current_line = ""
                    else:
                        result_lines.append(current_line)
                        current_line = ch
                else:
                    result_lines.append(ch)
                    current_line = ""

            if current_line:
                result_lines.append(current_line)

        return result_lines

    # =========================================================
    # 分页
    # =========================================================

    def paginate_lines(self, lines, body_height, line_height):
        """
        根据正文框高度把排版后的行切成多页。
        每一页继续使用完全相同的正文框。
        """
        body_height = float(body_height)
        line_height = float(line_height)

        if line_height <= 0:
            raise ValueError("行距必须大于 0")

        lines_per_page = int(math.floor(body_height / line_height))

        if lines_per_page < 1:
            raise ValueError("正文框高度太小，至少要能放下一行文字")

        if not lines:
            return [[]]

        pages = []
        for start in range(0, len(lines), lines_per_page):
            pages.append(lines[start:start + lines_per_page])

        return pages

    # =========================================================
    # 逐字直接绘制到最终 RGB 图片
    # =========================================================

    def draw_text_line(
        self,
        draw,
        text,
        font,
        x,
        y,
        max_width,
        letter_spacing=0,
        char_jitter=0,
    ):
        """
        直接在最终图片的指定位置绘制一行文字。
        不创建额外透明图层。
        """
        x = float(x)
        y = float(y)
        max_width = max(1.0, float(max_width))
        letter_spacing = float(letter_spacing)
        char_jitter = max(0.0, float(char_jitter))

        # 保持与原实现一致的左右抖动边距逻辑。
        jitter_margin = char_jitter
        current_x = jitter_margin
        usable_width = max(1.0, max_width - jitter_margin * 2)

        for ch in str(text):
            char_width = self.measure_char_width(draw, ch, font)

            if char_jitter:
                draw_x = x + current_x + random.uniform(
                    -char_jitter,
                    char_jitter,
                )
            else:
                draw_x = x + current_x

            draw.text(
                (draw_x, y),
                ch,
                font=font,
                fill=(0, 0, 0),
            )

            current_x += char_width + letter_spacing

            if current_x > usable_width:
                break

    # =========================================================
    # 直接绘制 4 个单行字段
    # =========================================================

    def draw_fields_on_page(
        self,
        image,
        fields,
        boxes,
        font,
        letter_spacing,
        char_jitter,
    ):
        draw = ImageDraw.Draw(image)

        for field_name in ["病区", "姓名", "床号", "住院号"]:
            box = boxes.get(field_name)
            if not box:
                continue

            value = fields.get(field_name, "")

            self.draw_text_line(
                draw=draw,
                text=str(value),
                font=font,
                x=box.get("x", 0),
                y=box.get("y", 0),
                max_width=box.get("width", 1),
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
            )

    # =========================================================
    # 直接绘制一页正文
    # =========================================================

    def draw_body_lines(
        self,
        image,
        x,
        y,
        width,
        height,
        lines,
        font,
        line_height,
        letter_spacing=0,
        char_jitter=0,
        line_jitter=0,
    ):
        """
        直接把正文画到最终 RGB 图片上。
        不创建正文 RGBA layer。
        """
        x = float(x)
        y = float(y)
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        line_height = max(1.0, float(line_height))
        letter_spacing = float(letter_spacing)
        char_jitter = max(0.0, float(char_jitter))
        line_jitter = max(0.0, float(line_jitter))

        draw = ImageDraw.Draw(image)
        current_y = 0.0

        for line in lines:
            if current_y + line_height > height:
                break

            if line == "":
                current_y += line_height
                continue

            if line_jitter:
                local_y = current_y + random.uniform(
                    -line_jitter,
                    line_jitter,
                )
                local_y = max(
                    0.0,
                    min(
                        local_y,
                        max(0.0, height - line_height),
                    ),
                )
            else:
                local_y = current_y

            self.draw_text_line(
                draw=draw,
                text=line,
                font=font,
                x=x,
                y=y + local_y,
                max_width=width,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
            )

            current_y += line_height

    # =========================================================
    # 逐页生成最终 RGB 图片（推荐接口）
    # =========================================================

    def iter_images(self, text, fields, boxes, settings):
        """
        一页生成、一页 yield。

        关键点：
        - 背景直接转 RGB，而不是 RGBA；
        - 字段和正文直接写到最终 RGB 图片；
        - 不创建字段/正文透明图层；
        - 不再做整页 RGBA -> RGB 的额外复制。
        """
        font_name = settings.get("font")
        font_size = settings.get("font_size", 40)
        line_height = settings.get("line_height", float(font_size) * 1.5)
        letter_spacing = settings.get("letter_spacing", 0)
        char_jitter = settings.get("char_jitter", 0)
        line_jitter = settings.get("line_jitter", 0)

        font = self.get_pillow_font(font_name, font_size)

        body_box = boxes.get("正文")
        if not body_box:
            raise ValueError("缺少正文框")

        body_width = float(body_box.get("width", 1))
        body_height = float(body_box.get("height", 1))

        # 小图只用于计算文字宽度，内存占用很小。
        measure_image = Image.new(
            "RGB",
            (max(1, int(round(body_width))), 100),
            "white",
        )

        try:
            measure_draw = ImageDraw.Draw(measure_image)
            wrap_width = max(
                1.0,
                body_width - float(char_jitter) * 2,
            )

            lines = self.wrap_text(
                draw=measure_draw,
                text=text,
                font=font,
                max_width=wrap_width,
                letter_spacing=letter_spacing,
            )
        finally:
            measure_image.close()

        page_lines = self.paginate_lines(
            lines=lines,
            body_height=body_height,
            line_height=line_height,
        )

        page_count = len(page_lines)

        for page_index, lines_for_page in enumerate(page_lines, start=1):
            print(
                f"[ImageGenerator] 开始生成第 {page_index}/{page_count} 页",
                flush=True,
            )

            # Image.open 是惰性读取；convert("RGB") 后得到本页唯一的大画布。
            with Image.open(self.background_image) as background:
                image = background.convert("RGB")

            print(
                f"[ImageGenerator] 背景尺寸={image.size}, mode={image.mode}",
                flush=True,
            )

            self.draw_fields_on_page(
                image=image,
                fields=fields,
                boxes=boxes,
                font=font,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
            )

            self.draw_body_lines(
                image=image,
                x=body_box.get("x", 0),
                y=body_box.get("y", 0),
                width=body_box.get("width", 1),
                height=body_box.get("height", 1),
                lines=lines_for_page,
                font=font,
                line_height=line_height,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
                line_jitter=line_jitter,
            )

            # 调用方保存完成后负责 close()。
            yield image

    # =========================================================
    # 兼容旧代码
    # =========================================================

    def create_images(self, text, fields, boxes, settings):
        """
        兼容旧调用：返回所有页面的 list。

        注意：预览接口不要调用这个方法，因为 list 会让多页图片
        同时驻留内存。预览请使用 iter_images()。
        """
        return list(
            self.iter_images(
                text=text,
                fields=fields,
                boxes=boxes,
                settings=settings,
            )
        )

    def create_image_preview(self, text, fields, boxes, settings):
        """兼容旧调用：只返回第一页。"""
        generator = self.iter_images(
            text=text,
            fields=fields,
            boxes=boxes,
            settings=settings,
        )

        try:
            return next(generator)
        except StopIteration:
            raise RuntimeError("未生成任何预览图片")
        finally:
            generator.close()
