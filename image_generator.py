from PIL import Image, ImageDraw, ImageFont

import math
import random
from statistics import median


try:
    RESAMPLE_BOX = Image.Resampling.BOX
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # 兼容较旧版本 Pillow
    RESAMPLE_BOX = Image.BOX
    RESAMPLE_LANCZOS = Image.LANCZOS


class ImageGenerator:
    """
    手写体图片生成器。

    设计原则：
    1. 最终页面始终在单张 RGB 图片上直接绘制，避免整页 RGBA 图层带来的高内存。
    2. 正文优先自动识别底图横线，每条横线对应一行，文字贴近该行线向上书写。
    3. 病区/姓名/床号/住院号等单行字段自动适配框宽：
       先减字距，再减字号，必要时做轻微横向压缩，保证不写出框。
    4. 如果横线识别失败，自动回退到原来的固定 line_height 排版，不影响可用性。
    """

    def __init__(self, font_manager, background_image):
        self.font_manager = font_manager
        self.background_image = background_image

        # 同一个模板/正文框通常会重复使用。
        # 横线检测只做一次，后续直接复用，减少 Render CPU 开销。
        self._line_cache = {}

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
    # 文字测量
    # =========================================================

    def measure_char_width(self, draw, ch, font):
        if not ch:
            return 0.0

        try:
            return float(draw.textlength(ch, font=font))
        except AttributeError:
            bbox = draw.textbbox((0, 0), ch, font=font)
            return float(bbox[2] - bbox[0])

    def measure_text_width(self, draw, text, font, letter_spacing=0):
        if not text:
            return 0.0

        text = str(text)
        total = 0.0
        letter_spacing = float(letter_spacing)

        for index, ch in enumerate(text):
            total += self.measure_char_width(draw, ch, font)
            if index < len(text) - 1:
                total += letter_spacing

        return total

    def get_text_bbox(self, font, text="国Ag0123，。"):
        """返回字体文字 bbox；用于纵向安全判断和视觉居中。"""
        text = str(text or "国")

        try:
            bbox = font.getbbox(text)
        except AttributeError:
            # 极老 Pillow 的兼容兜底。
            left, top = 0, 0
            width, height = font.getsize(text)
            bbox = (left, top, left + width, top + height)

        return tuple(float(v) for v in bbox)

    def get_text_height(self, font, text="国Ag0123，。"):
        bbox = self.get_text_bbox(font, text)
        return max(1.0, bbox[3] - bbox[1])

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
    # 普通固定行距分页（横线识别失败时回退使用）
    # =========================================================

    def paginate_lines(self, lines, body_height, line_height):
        body_height = float(body_height)
        line_height = float(line_height)

        if line_height <= 0:
            raise ValueError("行距必须大于 0")

        lines_per_page = int(math.floor(body_height / line_height))

        if lines_per_page < 1:
            raise ValueError("正文框高度太小，至少要能放下一行文字")

        return self.paginate_by_count(lines, lines_per_page)

    def paginate_by_count(self, lines, lines_per_page):
        lines_per_page = max(1, int(lines_per_page))

        if not lines:
            return [[]]

        pages = []
        for start in range(0, len(lines), lines_per_page):
            pages.append(lines[start:start + lines_per_page])

        return pages

    # =========================================================
    # 横线检测
    # =========================================================

    def _line_cache_key(self, body_box):
        return (
            int(round(float(body_box.get("x", 0)))),
            int(round(float(body_box.get("y", 0)))),
            int(round(float(body_box.get("width", 1)))),
            int(round(float(body_box.get("height", 1)))),
        )

    def _group_consecutive_rows(self, rows, max_gap=2):
        if not rows:
            return []

        groups = [[rows[0]]]

        for y in rows[1:]:
            if y - groups[-1][-1] <= max_gap:
                groups[-1].append(y)
            else:
                groups.append([y])

        return [sum(group) / len(group) for group in groups]

    def _scan_horizontal_lines_once(
        self,
        gray,
        dark_threshold,
        min_coverage,
    ):
        """
        gray 是正文区域灰度图。

        先只在水平方向缩小到最多 800px，保留原始高度，
        这样不会把 1~2px 的细横线在纵向缩没。
        然后把每一行压成 1 个像素，快速获得该行的黑色覆盖比例。
        """
        width, height = gray.size

        if width <= 0 or height <= 0:
            return []

        scan_width = min(800, width)

        if scan_width != width:
            scan = gray.resize(
                (scan_width, height),
                resample=RESAMPLE_BOX,
            )
        else:
            scan = gray.copy()

        # 去掉左右少量边缘，避免正文框边框、竖线干扰。
        side_margin = max(0, int(round(scan_width * 0.04)))
        if scan_width - side_margin * 2 >= 20:
            inner = scan.crop(
                (side_margin, 0, scan_width - side_margin, height)
            )
            scan.close()
            scan = inner

        # 暗色像素 -> 0，白色像素 -> 255。
        binary = scan.point(
            lambda p: 0 if p < dark_threshold else 255,
            mode="L",
        )
        scan.close()

        # BOX 缩成 1px 宽后，每一行的值就是该行的平均亮度。
        projection = binary.resize(
            (1, height),
            resample=RESAMPLE_BOX,
        )
        binary.close()

        candidate_rows = []
        limit = 255.0 * (1.0 - float(min_coverage))

        values = list(projection.getdata())
        projection.close()

        for y, value in enumerate(values):
            if value <= limit:
                candidate_rows.append(y)

        return self._group_consecutive_rows(candidate_rows)

    def detect_horizontal_lines(self, body_box):
        """
        自动识别正文框中的横线。

        返回值为相对于正文框顶部的 y 坐标列表。
        识别失败返回 []，上层会自动退回固定 line_height。
        """
        key = self._line_cache_key(body_box)

        if key in self._line_cache:
            return list(self._line_cache[key])

        box_x, box_y, box_w, box_h = key

        if box_w <= 1 or box_h <= 1:
            self._line_cache[key] = []
            return []

        try:
            with Image.open(self.background_image) as background:
                image_w, image_h = background.size

                left = max(0, box_x)
                top = max(0, box_y)
                right = min(image_w, box_x + box_w)
                bottom = min(image_h, box_y + box_h)

                if right - left < 20 or bottom - top < 20:
                    self._line_cache[key] = []
                    return []

                crop = background.crop(
                    (left, top, right, bottom)
                ).convert("L")

            try:
                # 第一轮比较严格；识别不到时再放宽。
                line_positions = self._scan_horizontal_lines_once(
                    crop,
                    dark_threshold=215,
                    min_coverage=0.35,
                )

                if len(line_positions) < 2:
                    line_positions = self._scan_horizontal_lines_once(
                        crop,
                        dark_threshold=230,
                        min_coverage=0.25,
                    )
            finally:
                crop.close()

        except Exception as e:
            print(
                f"[ImageGenerator] 横线检测失败，回退固定行距: {e}",
                flush=True,
            )
            self._line_cache[key] = []
            return []

        # 排除非常靠近的重复线/噪声。
        clean = []
        for y in sorted(line_positions):
            if not clean or y - clean[-1] >= 4:
                clean.append(float(y))

        self._line_cache[key] = clean
        return list(clean)

    def build_line_guides(self, line_positions):
        """
        将横线 [y1, y2, y3...] 转成“按行线书写”的引导信息。

        规则：
        - 每一条横线对应一行文字；
        - 第1行对应第1条横线；
        - 第i行的书写带是 (上一条线, 当前线)；
        - 第1行没有上一条线时，用“第一条线 - 典型行距”构造一个虚拟上边界。

        返回：
        guides=[(upper, line_y), ...], pitch, cleaned_lines
        其中 line_y 是该行对应的行线位置，upper 是这一行可写带的上边界。
        """
        if len(line_positions) < 2:
            return [], None, []

        gaps = [
            line_positions[i + 1] - line_positions[i]
            for i in range(len(line_positions) - 1)
            if line_positions[i + 1] - line_positions[i] >= 8
        ]

        if not gaps:
            return [], None, []

        pitch = float(median(gaps))
        min_gap = max(8.0, pitch * 0.55)
        max_gap = pitch * 1.55

        cleaned = [float(line_positions[0])]
        for i in range(1, len(line_positions)):
            gap = float(line_positions[i] - line_positions[i - 1])
            if min_gap <= gap <= max_gap:
                cleaned.append(float(line_positions[i]))

        if len(cleaned) < 2:
            return [], None, []

        guides = []
        for index, line_y in enumerate(cleaned):
            if index == 0:
                upper = max(0.0, line_y - pitch)
            else:
                upper = cleaned[index - 1]
            guides.append((float(upper), float(line_y)))

        return guides, pitch, cleaned

    # =========================================================
    # 字体根据行线间距自动限制
    # =========================================================

    def fit_body_font_to_guides(
        self,
        font_name,
        requested_size,
        guides,
        top_safety_ratio=0.08,
        bottom_clearance_ratio=0.04,
    ):
        """
        正文按“每条横线对应一行”排版。

        每一行文字的底部贴近该行线，但会留出少量底部安全边距，
        防止横线穿字。
        """
        requested_size = max(1, int(round(float(requested_size))))

        if not guides:
            return self.get_pillow_font(font_name, requested_size), requested_size

        band_heights = [line_y - upper for upper, line_y in guides]
        typical_height = float(median(band_heights))

        top_safety = max(0.0, min(0.30, float(top_safety_ratio)))
        bottom_clearance = max(0.0, min(0.30, float(bottom_clearance_ratio)))

        max_glyph_height = typical_height * max(
            0.10,
            1.0 - top_safety - bottom_clearance,
        )

        size = requested_size
        font = self.get_pillow_font(font_name, size)
        glyph_height = self.get_text_height(font)

        if glyph_height <= max_glyph_height:
            return font, size

        estimated = max(
            1,
            int(math.floor(size * max_glyph_height / glyph_height)),
        )
        size = min(size, estimated)
        font = self.get_pillow_font(font_name, size)

        while size > 1 and self.get_text_height(font) > max_glyph_height:
            size -= 1
            font = self.get_pillow_font(font_name, size)

        return font, size

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
    直接在最终图片指定位置绘制一行文字。
    不创建整页透明图层。

    这一版修正了“字段自动适配后最后几个字被截掉”的问题：
    fit_single_line_field() 的宽度判断和这里的实际绘制边界保持一致。
         """
        x = float(x)
        y = float(y)
        max_width = max(1.0, float(max_width))
        letter_spacing = float(letter_spacing)
        char_jitter = max(0.0, float(char_jitter))

        text = str(text)

    # 左右各预留一份抖动边距
        left_margin = char_jitter
        right_limit = max_width - char_jitter

        current_x = left_margin

        for index, ch in enumerate(text):
            char_width = self.measure_char_width(draw, ch, font)

        # 判断这个字符画进去后是否会越过右边界
            if current_x + char_width > right_limit + 1e-6:
                break

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

            current_x += char_width

            if index < len(text) - 1:
                current_x += letter_spacing

    # =========================================================
    # 单行字段自动适配
    # =========================================================

    def _field_text_width(
        self,
        draw,
        text,
        font,
        letter_spacing,
        char_jitter,
    ):
        return (
            self.measure_text_width(
                draw,
                text,
                font,
                letter_spacing,
            )
            + max(0.0, float(char_jitter)) * 2.0
        )

    def fit_single_line_field(
        self,
        draw,
        text,
        font_name,
        base_font_size,
        base_letter_spacing,
        box_width,
        box_height,
        char_jitter=0,
        min_font_ratio=0.65,
        min_horizontal_scale=0.90,
        padding_ratio=0.035,
    ):
        """
        单行字段自动适配：
        1. 保持字号，优先减少字距；
        2. 还放不下，再缩小字号；
        3. 仍有轻微超宽时，允许最多少量横向压缩；
        4. 极端情况下继续缩字号，最终保证不越框。
        """
        text = str(text or "")
        base_font_size = max(1, int(round(float(base_font_size))))
        base_letter_spacing = float(base_letter_spacing)
        box_width = max(1.0, float(box_width))
        box_height = max(1.0, float(box_height))
        char_jitter = max(0.0, float(char_jitter))

        padding = max(
            2.0,
            min(
                box_width * max(0.0, float(padding_ratio)),
                base_font_size * 0.30,
            ),
        )
        usable_width = max(1.0, box_width - padding * 2.0)
        usable_height = max(1.0, box_height * 0.92)

        # 最低字距：允许适度负字距，但不让字符严重堆叠。
        min_spacing = min(
            base_letter_spacing,
            -base_font_size * 0.08,
        )

        min_size = max(
            1,
            int(round(base_font_size * float(min_font_ratio))),
        )

        def choose_spacing(font):
            if len(text) <= 1:
                return base_letter_spacing

            char_sum = sum(
                self.measure_char_width(draw, ch, font)
                for ch in text
            )
            available_for_spacing = (
                usable_width
                - char_jitter * 2.0
                - char_sum
            )
            fit_spacing = available_for_spacing / (len(text) - 1)

            return max(
                min_spacing,
                min(base_letter_spacing, fit_spacing),
            )

        def fits(font, spacing, horizontal_scale=1.0):
            width = self._field_text_width(
                draw,
                text,
                font,
                spacing,
                char_jitter,
            ) * horizontal_scale

            height = self.get_text_height(font, text or "国")

            return (
                width <= usable_width + 0.5
                and height <= usable_height + 0.5
            )

        # ---------- 1. 原字号，先自动压字距 ----------
        font = self.get_pillow_font(font_name, base_font_size)
        spacing = choose_spacing(font)

        if fits(font, spacing):
            return {
                "font": font,
                "font_size": base_font_size,
                "letter_spacing": spacing,
                "horizontal_scale": 1.0,
                "padding": padding,
                "usable_width": usable_width,
            }

        # ---------- 2. 缩字号，在 >= min_size 范围内找最大的可用字号 ----------
        low = min_size
        high = base_font_size
        best = None

        while low <= high:
            mid = (low + high) // 2
            mid_font = self.get_pillow_font(font_name, mid)
            mid_spacing = choose_spacing(mid_font)

            if fits(mid_font, mid_spacing):
                best = (mid, mid_font, mid_spacing)
                low = mid + 1
            else:
                high = mid - 1

        if best is not None:
            size, font, spacing = best
            return {
                "font": font,
                "font_size": size,
                "letter_spacing": spacing,
                "horizontal_scale": 1.0,
                "padding": padding,
                "usable_width": usable_width,
            }

        # ---------- 3. 到最小推荐字号仍超宽，尝试轻微横向压缩 ----------
        size = min_size
        font = self.get_pillow_font(font_name, size)
        spacing = choose_spacing(font)
        natural_width = self._field_text_width(
            draw,
            text,
            font,
            spacing,
            char_jitter,
        )

        if natural_width > 0:
            required_scale = min(1.0, usable_width / natural_width)
        else:
            required_scale = 1.0

        if (
            required_scale >= float(min_horizontal_scale)
            and self.get_text_height(font, text or "国") <= usable_height + 0.5
        ):
            return {
                "font": font,
                "font_size": size,
                "letter_spacing": spacing,
                "horizontal_scale": required_scale,
                "padding": padding,
                "usable_width": usable_width,
            }

        # ---------- 4. 极端长字段：继续缩字号，确保一定放得下 ----------
        for size in range(min_size - 1, 0, -1):
            font = self.get_pillow_font(font_name, size)
            spacing = choose_spacing(font)
            natural_width = self._field_text_width(
                draw,
                text,
                font,
                spacing,
                char_jitter,
            )
            height_ok = (
                self.get_text_height(font, text or "国")
                <= usable_height + 0.5
            )

            if natural_width <= usable_width + 0.5 and height_ok:
                return {
                    "font": font,
                    "font_size": size,
                    "letter_spacing": spacing,
                    "horizontal_scale": 1.0,
                    "padding": padding,
                    "usable_width": usable_width,
                }

            if natural_width > 0:
                required_scale = min(1.0, usable_width / natural_width)
            else:
                required_scale = 1.0

            if (
                required_scale >= float(min_horizontal_scale)
                and height_ok
            ):
                return {
                    "font": font,
                    "font_size": size,
                    "letter_spacing": spacing,
                    "horizontal_scale": required_scale,
                    "padding": padding,
                    "usable_width": usable_width,
                }

        # 理论上不会走到这里；最后返回 1px 字体作为绝对兜底。
        font = self.get_pillow_font(font_name, 1)
        return {
            "font": font,
            "font_size": 1,
            "letter_spacing": 0.0,
            "horizontal_scale": 1.0,
            "padding": padding,
            "usable_width": usable_width,
        }

    def _draw_scaled_field_text(
        self,
        image,
        text,
        font,
        x,
        y,
        natural_width,
        target_width,
        letter_spacing,
        char_jitter,
        box_height,
    ):
        """
        只为一个字段创建很小的透明图层并横向压缩。
        这不是整页 RGBA 图层，内存开销很小。
        """
        layer_width = max(1, int(math.ceil(natural_width + 4)))
        layer_height = max(
            1,
            int(math.ceil(max(float(box_height), self.get_text_height(font) * 1.8))),
        )

        layer = Image.new(
            "RGBA",
            (layer_width, layer_height),
            (0, 0, 0, 0),
        )

        try:
            layer_draw = ImageDraw.Draw(layer)
            self.draw_text_line(
                draw=layer_draw,
                text=text,
                font=font,
                x=0,
                y=0,
                max_width=layer_width,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
            )

            resized_width = max(1, int(round(target_width)))
            resized = layer.resize(
                (resized_width, layer_height),
                resample=RESAMPLE_LANCZOS,
            )

            try:
                image.paste(
                    resized,
                    (int(round(x)), int(round(y))),
                    resized,
                )
            finally:
                resized.close()
        finally:
            layer.close()

    # =========================================================
    # 直接绘制 4 个单行字段
    # =========================================================

    def draw_fields_on_page(
        self,
        image,
        fields,
        boxes,
        font_name,
        font_size,
        letter_spacing,
        char_jitter,
        auto_fit=True,
        min_font_ratio=0.65,
        min_horizontal_scale=0.90,
    ):
        draw = ImageDraw.Draw(image)

        for field_name in ["病区", "姓名", "床号", "住院号"]:
            box = boxes.get(field_name)
            if not box:
                continue

            value = str(fields.get(field_name, "") or "")
            if not value:
                continue

            box_x = float(box.get("x", 0))
            box_y = float(box.get("y", 0))
            box_width = max(1.0, float(box.get("width", 1)))
            box_height = max(1.0, float(box.get("height", font_size * 1.5)))

            if not auto_fit:
                font = self.get_pillow_font(font_name, font_size)
                self.draw_text_line(
                    draw=draw,
                    text=value,
                    font=font,
                    x=box_x,
                    y=box_y,
                    max_width=box_width,
                    letter_spacing=letter_spacing,
                    char_jitter=char_jitter,
                )
                continue

            fit = self.fit_single_line_field(
                draw=draw,
                text=value,
                font_name=font_name,
                base_font_size=font_size,
                base_letter_spacing=letter_spacing,
                box_width=box_width,
                box_height=box_height,
                char_jitter=char_jitter,
                min_font_ratio=min_font_ratio,
                min_horizontal_scale=min_horizontal_scale,
            )

            fitted_font = fit["font"]
            fitted_size = fit["font_size"]
            fitted_spacing = fit["letter_spacing"]
            horizontal_scale = fit["horizontal_scale"]
            padding = fit["padding"]
            usable_width = fit["usable_width"]

            if (
                fitted_size != int(round(float(font_size)))
                or abs(fitted_spacing - float(letter_spacing)) > 0.1
                or horizontal_scale < 0.999
            ):
                print(
                    f"[ImageGenerator] 字段自动适配 {field_name}: "
                    f"字号={fitted_size}, 字距={fitted_spacing:.2f}, "
                    f"横向比例={horizontal_scale:.3f}",
                    flush=True,
                )

            if horizontal_scale >= 0.999:
                self.draw_text_line(
                    draw=draw,
                    text=value,
                    font=fitted_font,
                    x=box_x + padding,
                    y=box_y,
                    max_width=usable_width,
                    letter_spacing=fitted_spacing,
                    char_jitter=char_jitter,
                )
            else:
                natural_width = self._field_text_width(
                    draw,
                    value,
                    fitted_font,
                    fitted_spacing,
                    char_jitter,
                )
                target_width = min(
                    usable_width,
                    natural_width * horizontal_scale,
                )

                self._draw_scaled_field_text(
                    image=image,
                    text=value,
                    font=fitted_font,
                    x=box_x + padding,
                    y=box_y,
                    natural_width=natural_width,
                    target_width=target_width,
                    letter_spacing=fitted_spacing,
                    char_jitter=char_jitter,
                    box_height=box_height,
                )

    # =========================================================
    # 正文：横线自动对齐模式
    # =========================================================

    def draw_body_lines_on_ruled_lines(
        self,
        image,
        x,
        y,
        width,
        lines,
        font,
        guides,
        letter_spacing=0,
        char_jitter=0,
        line_jitter=0,
        bottom_ratio=0.96,
        top_safety_ratio=0.08,
        bottom_clearance_ratio=0.04,
    ):
        """
        每条横线对应一行文字。

        guides 中的每一项都是 (upper, line_y)：
        - upper: 该行可写带上边界
        - line_y: 该行对应的行线位置

        写法：
        - 文字“属于”这条 line_y；
        - 文字底部贴近该行线，但略微上移，避免行线穿字；
        - 第一行也直接对应第一条行线，而不是写在第一、二条线之间。
        """
        x = float(x)
        y = float(y)
        width = max(1.0, float(width))
        letter_spacing = float(letter_spacing)
        char_jitter = max(0.0, float(char_jitter))
        line_jitter = max(0.0, float(line_jitter))
        bottom_ratio = max(0.75, min(0.99, float(bottom_ratio)))
        top_safety_ratio = max(0.0, min(0.30, float(top_safety_ratio)))
        bottom_clearance_ratio = max(0.0, min(0.30, float(bottom_clearance_ratio)))

        draw = ImageDraw.Draw(image)

        for line, guide in zip(lines, guides):
            upper, line_y = guide
            band_height = max(1.0, line_y - upper)

            # 空行仍然占用一条行线。
            if line == "":
                continue

            bbox = self.get_text_bbox(font, line)
            glyph_top = bbox[1]
            glyph_bottom = bbox[3]
            glyph_height = max(1.0, glyph_bottom - glyph_top)

            # 目标：字的底部位于该行带下部，贴近当前行线。
            desired_bottom = upper + band_height * bottom_ratio

            if line_jitter:
                desired_bottom += random.uniform(
                    -line_jitter,
                    line_jitter,
                )

            min_top = upper + band_height * top_safety_ratio
            max_bottom = line_y - band_height * bottom_clearance_ratio

            draw_top = desired_bottom - glyph_height
            draw_bottom = desired_bottom

            if draw_top < min_top:
                shift = min_top - draw_top
                draw_top += shift
                draw_bottom += shift

            if draw_bottom > max_bottom:
                shift = draw_bottom - max_bottom
                draw_top -= shift
                draw_bottom -= shift

            # 最终兜底：如果空间仍然不够，至少保证底部不压线。
            draw_bottom = min(draw_bottom, max_bottom)
            draw_y = y + draw_bottom - glyph_bottom

            self.draw_text_line(
                draw=draw,
                text=line,
                font=font,
                x=x,
                y=draw_y,
                max_width=width,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
            )

    # =========================================================
    # 正文：原固定 line_height 回退模式
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
        横线无法识别时使用原固定行距逻辑。
        仍直接画在最终 RGB 图片上。
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

        保留低内存结构：
        - 背景直接转 RGB；
        - 正文直接写到 RGB；
        - 单行字段通常也直接写到 RGB；
        - 只有极少数需要横向压缩的字段会创建一个很小的临时 RGBA 层；
        - 不创建整页 RGBA 图层；
        - 不把多页图片同时保存在内存中。
        """
        font_name = settings.get("font")
        requested_font_size = settings.get("font_size", 40)
        requested_line_height = settings.get(
            "line_height",
            float(requested_font_size) * 1.5,
        )
        letter_spacing = settings.get("letter_spacing", 0)
        char_jitter = settings.get("char_jitter", 0)
        line_jitter = settings.get("line_jitter", 0)

        # 新功能默认开启；以后如果前端需要，也可以显式传 false 关闭。
        auto_line_align = bool(settings.get("auto_line_align", True))
        auto_fit_fields = bool(settings.get("auto_fit_fields", True))

        # 正文按行线书写：每条横线对应一行，文字底部贴近该行线。
        body_bottom_ratio = float(
            settings.get("body_bottom_ratio", 0.96)
        )
        body_top_safety_ratio = float(
            settings.get("body_top_safety_ratio", 0.08)
        )
        body_line_clearance_ratio = float(
            settings.get("body_line_clearance_ratio", 0.04)
        )

        # 长字段适配参数。
        field_min_font_ratio = float(
            settings.get("field_min_font_ratio", 0.65)
        )
        field_min_horizontal_scale = float(
            settings.get("field_min_horizontal_scale", 0.90)
        )

        body_box = boxes.get("正文")
        if not body_box:
            raise ValueError("缺少正文框")

        body_width = max(1.0, float(body_box.get("width", 1)))
        body_height = max(1.0, float(body_box.get("height", 1)))

        # -----------------------------------------------------
        # 1. 尝试识别正文横线并确定正文实际字号/每页行数
        # -----------------------------------------------------
        line_guides = []
        detected_pitch = None
        cleaned_lines = []

        if auto_line_align:
            line_positions = self.detect_horizontal_lines(body_box)
            line_guides, detected_pitch, cleaned_lines = self.build_line_guides(line_positions)

        if line_guides:
            body_font, actual_body_font_size = self.fit_body_font_to_guides(
                font_name=font_name,
                requested_size=requested_font_size,
                guides=line_guides,
                top_safety_ratio=body_top_safety_ratio,
                bottom_clearance_ratio=body_line_clearance_ratio,
            )

            print(
                f"[ImageGenerator] 正文按行线自动对齐: "
                f"检测到{len(line_positions)}条横线, "
                f"有效书写行={len(line_guides)}, "
                f"估计行距={detected_pitch:.1f}px, "
                f"底部比例={body_bottom_ratio:.2f}, "
                f"正文字号={actual_body_font_size}",
                flush=True,
            )
        else:
            body_font = self.get_pillow_font(
                font_name,
                requested_font_size,
            )
            actual_body_font_size = int(round(float(requested_font_size)))

            if auto_line_align:
                print(
                    "[ImageGenerator] 未可靠识别正文横线，"
                    "使用固定 line_height 回退模式",
                    flush=True,
                )

        # -----------------------------------------------------
        # 2. 用最终实际正文字号进行自动换行
        # -----------------------------------------------------
        measure_image = Image.new(
            "RGB",
            (max(1, int(round(body_width))), 100),
            "white",
        )

        try:
            measure_draw = ImageDraw.Draw(measure_image)
            wrap_width = max(
                1.0,
                body_width - float(char_jitter) * 2.0,
            )

            lines = self.wrap_text(
                draw=measure_draw,
                text=text,
                font=body_font,
                max_width=wrap_width,
                letter_spacing=letter_spacing,
            )
        finally:
            measure_image.close()

        # -----------------------------------------------------
        # 3. 分页
        # -----------------------------------------------------
        if line_guides:
            page_lines = self.paginate_by_count(
                lines,
                len(line_guides),
            )
        else:
            page_lines = self.paginate_lines(
                lines=lines,
                body_height=body_height,
                line_height=requested_line_height,
            )

        page_count = len(page_lines)

        # -----------------------------------------------------
        # 4. 一页一页生成，保持低峰值内存
        # -----------------------------------------------------
        for page_index, lines_for_page in enumerate(page_lines, start=1):
            print(
                f"[ImageGenerator] 开始生成第 {page_index}/{page_count} 页",
                flush=True,
            )

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
                font_name=font_name,
                font_size=requested_font_size,
                letter_spacing=letter_spacing,
                char_jitter=char_jitter,
                auto_fit=auto_fit_fields,
                min_font_ratio=field_min_font_ratio,
                min_horizontal_scale=field_min_horizontal_scale,
            )

            if line_guides:
                self.draw_body_lines_on_ruled_lines(
                    image=image,
                    x=body_box.get("x", 0),
                    y=body_box.get("y", 0),
                    width=body_box.get("width", 1),
                    lines=lines_for_page,
                    font=body_font,
                    guides=line_guides,
                    letter_spacing=letter_spacing,
                    char_jitter=char_jitter,
                    line_jitter=line_jitter,
                    bottom_ratio=body_bottom_ratio,
                    top_safety_ratio=body_top_safety_ratio,
                    bottom_clearance_ratio=body_line_clearance_ratio,
                )
            else:
                self.draw_body_lines(
                    image=image,
                    x=body_box.get("x", 0),
                    y=body_box.get("y", 0),
                    width=body_box.get("width", 1),
                    height=body_box.get("height", 1),
                    lines=lines_for_page,
                    font=body_font,
                    line_height=requested_line_height,
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
