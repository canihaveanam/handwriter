import os
import sys
from urllib.parse import quote
import datetime
import json   
# === 打包路径处理函数 ===
def get_resource_path(relative_path):
    """获取资源的绝对路径（支持打包和开发环境）"""
    try:
        # 打包后的环境
        base_path = sys._MEIPASS
    except AttributeError:
        # 开发环境
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    full_path = os.path.join(base_path, relative_path)
    return full_path
# === 结束路径处理函数 ===

from flask import Flask, request, send_file, render_template, jsonify, make_response
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import tempfile
import zipfile
from io import BytesIO
import random
import fitz
from PIL import Image
import io
import uuid
from font_manager import FontManager

app = Flask(__name__, template_folder=get_resource_path("."))

font_manager = FontManager(
    get_resource_path,
    fonts_dir="fonts",
    default_font="StyleA"
)

class PDFGenerator:
    def __init__(self, font_manager):
        self.background_image = get_resource_path("base.jpg")
        self.font_manager = font_manager



    def create_pdf_with_preview(self, text, fields=None, settings=None):
        if settings is None:
            settings = {}

        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)

        font_size = settings.get("font_size", 15)
        selected_font = settings.get("font")

        font_name = self.font_manager.get_reportlab_font_name(selected_font)
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


generator = PDFGenerator(font_manager)
def get_log_dir():
    if getattr(sys, 'frozen', False):
        # 打包后：exe 所在目录（不是 _MEIPASS 临时目录）
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "logs")


def write_log(action, ip, filename):
    """
    记录操作日志
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_dir = get_log_dir()
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "operation.log")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            f"{now} | "
            f"IP={ip} | "
            f"操作={action} | "
            f"文件={filename}\n"
        )


# 保存当前生成文件的信息
tasks = {}# =========================================
# 🟢 PDF → PNG 图片
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
# 预览接口
# =========================================
@app.route("/")
def index():
    return render_template("index.html")
# =========================================
# 模板接口
# =========================================
def get_template_path():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "template.json")

# =========================================
# 字体接口
# =========================================

@app.route("/template", methods=["GET"])
def get_template():
    try:
        path = get_template_path()
        if not os.path.exists(path):
            return jsonify({
                "success": True,
                "text": "",
                "病区": "",
                "姓名": "",
                "床号": "",
                "住院号": ""
            })

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return jsonify({"success": True, **data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/fonts", methods=["GET"])
def get_fonts():
    try:
        fonts = font_manager.list_fonts()
        default_font = font_manager.get_default_font()

        return jsonify({
            "success": True,
            "fonts": fonts,
            "default": default_font
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "fonts": [],
            "default": None,
            "error": str(e)
        })


@app.route("/preview", methods=["POST"])
def preview_pdf():

    

    try:
        task_id = str(uuid.uuid4())
        data = request.get_json()

        text = data.get("text", "")
        fields = data.get("fields", {})
        settings = data.get("settings", {})


        # 保存姓名和住院号
        tasks[task_id] = {
            "name": fields.get("姓名", "未知"),
            "patient_id": fields.get("住院号", "未知")
        }


        pdf_buffer = generator.create_pdf_with_preview(
            text,
            fields,
            settings
        )


        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False
        ) as f:

            f.write(pdf_buffer.getvalue())
            path = f.name

        write_log("预览PDF", request.remote_addr, os.path.basename(path))

        return jsonify({
            "success": True,
            "preview_url":
                "/view_pdf/" + os.path.basename(path),
            "task_id": task_id
        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error": str(e)

        })

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
# 下载 PDF 的 PNG 图片
# =========================================
@app.route("/download_images/<task_id>/<filename>")
def download_images(task_id, filename):

    print("进入新的下载接口", flush=True)
    info = tasks.get(task_id)

    print(info, flush=True)

    if not info:
        return "任务不存在", 404

    path = os.path.join(
        tempfile.gettempdir(),
        filename
    )

    if not os.path.exists(path):
        return "文件不存在", 404

    with open(path, "rb") as f:
        pdf_bytes = f.read()

    images = pdf_to_images(pdf_bytes)

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, img in enumerate(images):
            img_buffer = BytesIO()
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(img_buffer, format="JPEG", quality=95)

            info = tasks.get(task_id)

            jpg_name = f"{info['name']}-{i+1}-{info['patient_id']}.jpg"
            zip_file.writestr(jpg_name, img_buffer.getvalue())

    zip_buffer.seek(0)

    zip_name = (
        f"{info['name']}-"
        f"{info['patient_id']}.zip"
    )

    write_log("下载zip图片包", request.remote_addr, zip_name)

    response = make_response(
        zip_buffer.getvalue()
    )

    response.headers["Content-Type"] = "application/zip"

    response.headers["Content-Disposition"] = (
        "attachment; filename*=UTF-8''"
        + quote(zip_name)
    )
    print(response.headers, flush=True)
   
    return response


# =========================================
# 查看 PDF文件
# =========================================
@app.route("/view_pdf/<filename>")
def view_pdf(filename):
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return send_file(path, mimetype="application/pdf")
    return "文件不存在", 404




if __name__ == "__main__":
    print("启动手写体文档生成器！！！：http://0.0.0.0:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
