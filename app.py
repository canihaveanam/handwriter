from flask import Flask, request, send_file, render_template, jsonify
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import os
import tempfile
from io import BytesIO
import random

app = Flask(__name__, template_folder=".")

class PDFGenerator:
    def __init__(self):
        self.background_image = "base.jpg"
        self.font_path = "handwrite.ttf"
        self.font_name = "HandwriteFont"

    def register_font(self):
        """注册字体"""
        try:
            if os.path.exists(self.font_path):
                pdfmetrics.registerFont(TTFont(self.font_name, self.font_path))
                return True
        except:
            pass
        return False

    def create_pdf_with_preview(self, text, fields=None, settings=None):
        if settings is None:
            settings = {}

        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)

        # 字体
        font_size = settings.get("font_size", 15)
        use_custom_font = self.register_font()
        font_name = self.font_name if use_custom_font else "Helvetica"
        c.setFont(font_name, font_size)

        # 页背景
        def draw_page_background():
            if os.path.exists(self.background_image):
                c.drawImage(self.background_image, 0, 0, width=A4[0], height=A4[1])

        # 页头字段
        def draw_header_fields():
            if not fields:
                return
            field_settings = settings.get("fields", {})
            for field, value in fields.items():
                if field in field_settings:
                    x = field_settings[field]["x"]
                    y = field_settings[field]["y"]
                    c.drawString(x, y, str(value))

        # 初始化第一页
        draw_page_background()
        draw_header_fields()

        # 文本参数
        start_x = settings.get("start_x", 64)
        start_y = settings.get("start_y", 661)
        line_height = settings.get("line_height", 30)
        y_position = start_y

        line_jitter = settings.get("line_jitter", 3)
        char_jitter = settings.get("char_jitter", 2)

        max_width = A4[0] - start_x - 70  # 右边距50
        punctuation = "，。！？：；、））》】"

        lines = text.split("\n")

        # =====================
        # 主循环：绘制文本
        # =====================
        for original_line in lines:

            line = original_line

            if not line.strip():
                y_position -= line_height
                continue

            while line:

                # 计算可容纳宽度
                cut = 1
                while cut <= len(line):
                    substring = line[:cut]
                    width = pdfmetrics.stringWidth(substring, font_name, font_size)
                    if width > max_width:
                        break
                    cut += 1
                cut -= 1
                if cut <= 0:
                    cut = 1

                # 行尾标点优化
                while cut > 0 and line[cut - 1] in punctuation:
                    cut -= 1
                if cut <= 0:
                    cut = 1

                # 避免标点出现在下一行开头
                if cut < len(line) and line[cut] in punctuation:
                    cut += 1
                cut = max(cut, 1)

                # 截取行内容
                draw_text = line[:cut]
                line = line[cut:]

                # 换页
                if y_position < 120:
                    c.showPage()
                    draw_page_background()
                    c.setFont(font_name, font_size)
                    draw_header_fields()
                    y_position = start_y

                # 行抖动
                jittered_y = y_position + random.randint(-line_jitter, line_jitter)

                # 字符逐字绘制（字抖动）
                current_x = start_x
                for ch in draw_text:
                    jittered_x = current_x + random.uniform(-char_jitter, char_jitter)
                    c.drawString(jittered_x, jittered_y, ch)
                    current_x += pdfmetrics.stringWidth(ch, font_name, font_size)

                y_position -= line_height

        c.save()
        pdf_buffer.seek(0)
        return pdf_buffer


generator = PDFGenerator()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/preview", methods=["POST"])
def preview_pdf():
    try:
        data = request.get_json()
        text = data.get("text", "")
        fields = data.get("fields", {})
        settings = data.get("settings", {})

        pdf_buffer = generator.create_pdf_with_preview(text, fields, settings)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_buffer.getvalue())
            path = f.name

        return jsonify({
            "success": True,
            "preview_url": "/view_pdf/" + os.path.basename(path)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/generate", methods=["POST"])
def generate_pdf():
    try:
        data = request.get_json()
        text = data.get("text", "")
        fields = data.get("fields", {})
        settings = data.get("settings", {})

        pdf_buffer = generator.create_pdf_with_preview(text, fields, settings)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_buffer.getvalue())
            path = f.name

        return jsonify({
            "success": True,
            "download_url": "/download/" + os.path.basename(path)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/view_pdf/<filename>")
def view_pdf(filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return send_file(path, mimetype="application/pdf")
    return "文件不存在", 404

@app.route("/download/<filename>")
def download_pdf(filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name="手写文档.pdf")
    return "文件不存在", 404


if __name__ == "__main__":
    print("启动手写体文档生成器：http://127.0.0.1:5001")
    app.run(debug=True, host="127.0.0.1", port=5001)
