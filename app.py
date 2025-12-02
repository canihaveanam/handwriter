from flask import Flask, request, send_file, render_template, jsonify
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import os
import tempfile
import zipfile
from io import BytesIO
import random
from pdf2image import convert_from_bytes  # 🟢 新增：PDF 转图片
import fitz
from PIL import Image
import io

app = Flask(__name__, template_folder=".")

class PDFGenerator:
    def __init__(self):
        self.background_image = "base.jpg"
        self.font_path = "handwrite.ttf"
        self.font_name = "HandwriteFont"

    def register_font(self):
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

        draw_page_background()
        draw_header_fields()

        start_x = settings.get("start_x", 64)
        start_y = settings.get("start_y", 661)
        line_height = settings.get("line_height", 30)
        y_position = start_y

        line_jitter = settings.get("line_jitter", 3)
        char_jitter = settings.get("char_jitter", 2)

        max_width = A4[0] - start_x - 70
        punctuation = "，。！？：；、））》】"

        lines = text.split("\n")

        for original_line in lines:
            line = original_line

            if not line.strip():
                y_position -= line_height
                continue

            while line:
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

                while cut > 0 and line[cut - 1] in punctuation:
                    cut -= 1
                if cut <= 0:
                    cut = 1

                if cut < len(line) and line[cut] in punctuation:
                    cut += 1
                cut = max(cut, 1)

                draw_text = line[:cut]
                line = line[cut:]

                if y_position < 120:
                    c.showPage()
                    draw_page_background()
                    c.setFont(font_name, font_size)
                    draw_header_fields()
                    y_position = start_y

                jittered_y = y_position + random.randint(-line_jitter, line_jitter)
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


# =========================================
# 🟢 新功能：PDF → PNG 图片（第一页）
# =========================================
def pdf_to_images(pdf_bytes):
    """将PDF所有页面转换为PNG图片列表"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 高质量转换
            mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
        
        doc.close()
        return images
        
    except Exception as e:
        # fallback: 创建错误提示图片
        img = Image.new('RGB', (800, 600), color='white')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), f"图片生成错误: {str(e)}", fill='red')
        return [img]

# =========================================
# 原有预览接口
# =========================================
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


# =========================================
# 原有 PDF 下载接口
# =========================================
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


# =========================================
# 新增：下载 PDF 的 PNG 图片
# =========================================
@app.route("/download_images/<filename>")
def download_images(filename):
    """下载所有页面图片为ZIP压缩包"""
    path = os.path.join(tempfile.gettempdir(), filename)
    if not os.path.exists(path):
        return "文件不存在", 404

    with open(path, "rb") as f:
        pdf_bytes = f.read()

    images = pdf_to_images(pdf_bytes)

    # 创建ZIP压缩包
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, img in enumerate(images):
            img_buffer = BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            zip_file.writestr(f"手写文档_第{i+1}页.png", img_buffer.getvalue())
    
    zip_buffer.seek(0)
    
    # 使用原文件名作为ZIP文件名的一部分
    original_name = os.path.splitext(filename)[0]
    download_name = f"{original_name}_所有页面.zip"
    
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/zip'
    )


# =========================================
# 查看 PDF
# =========================================
@app.route("/view_pdf/<filename>")
def view_pdf(filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return send_file(path, mimetype="application/pdf")
    return "文件不存在", 404


# =========================================
# 下载 PDF（原功能）
# =========================================
@app.route("/download/<filename>")
def download_pdf(filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name="手写文档.pdf")
    return "文件不存在", 404


if __name__ == "__main__":
    print("启动手写体文档生成器：http://127.0.0.1:5001")
    app.run(debug=True, host="127.0.0.1", port=5001)
