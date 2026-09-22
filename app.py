import atexit
import datetime
import os
import sys
import tempfile
import time
import uuid
import zipfile

from io import BytesIO
from urllib.parse import quote

from flask import (
    Flask,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
)
from PIL import Image

from font_manager import FontManager
from image_generator import ImageGenerator
from template_manager import create_template_blueprint


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


app = Flask(__name__, template_folder=get_resource_path("."))

font_manager = FontManager(
    get_resource_path,
    fonts_dir="fonts",
    default_font="StyleA",
)

image_generator = ImageGenerator(
    font_manager,
    get_resource_path("base.jpg"),
)


def get_log_dir():
    return os.path.join(get_app_dir(), "logs")


def write_log(action, ip, filename="-"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{now} | IP={ip} | 操作={action} | 文件={filename}"
    print(log_line, flush=True)

    log_dir = get_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "operation.log")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")


# =========================================================
# 模板 Blueprint
# =========================================================

app.register_blueprint(
    create_template_blueprint(
        get_app_dir=get_app_dir,
        write_log=write_log,
    )
)


# =========================================================
# 临时图片任务
# =========================================================

tasks = {}

# 只预览不下载时，临时 PNG 最多保存 1 小时。
TEMP_TASK_TTL_SECONDS = 60 * 60


def is_safe_temp_path(path):
    if not path:
        return False

    temp_root = os.path.realpath(tempfile.gettempdir())
    real_path = os.path.realpath(path)

    try:
        return os.path.commonpath([temp_root, real_path]) == temp_root
    except ValueError:
        return False


def remove_temp_file(path):
    if path and is_safe_temp_path(path) and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def cleanup_task(task_id):
    info = tasks.pop(task_id, None)
    if not info:
        return

    for path in info.get("image_paths", []):
        remove_temp_file(path)


def cleanup_expired_tasks():
    now = time.time()
    expired = []

    for task_id, info in list(tasks.items()):
        created_at = info.get("created_at", 0)
        if now - created_at >= TEMP_TASK_TTL_SECONDS:
            expired.append(task_id)

    for task_id in expired:
        cleanup_task(task_id)


def cleanup_all_tasks():
    for task_id in list(tasks.keys()):
        cleanup_task(task_id)


atexit.register(cleanup_all_tasks)


@app.before_request
def auto_cleanup_temp_files():
    cleanup_expired_tasks()


# =========================================================
# 首页 / 基础资源
# =========================================================

@app.route("/")
def index():
    write_log("访问主页", request.remote_addr, "-")
    return render_template("index.html")


@app.route("/base.jpg")
def base_image():
    return send_file(
        get_resource_path("base.jpg"),
        mimetype="image/jpeg",
    )


# =========================================================
# 字体
# =========================================================

@app.route("/api/fonts", methods=["GET"])
def get_fonts():
    try:
        fonts = font_manager.list_fonts()
        default_font = font_manager.get_default_font()

        return jsonify({
            "success": True,
            "fonts": fonts,
            "default": default_font,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "fonts": [],
            "default": None,
            "error": str(e),
        }), 500


# =========================================================
# Pillow 多页预览
# =========================================================

@app.route("/preview_image", methods=["POST"])
def preview_image():
    image_paths = []

    try:
        data = request.get_json(silent=True) or {}

        text = data.get("text", "")
        fields = data.get("fields", {})
        boxes = data.get("boxes", {})
        settings = data.get("settings", {})

        required_boxes = ["病区", "姓名", "床号", "住院号", "正文"]

        for name in required_boxes:
            if name not in boxes:
                return jsonify({
                    "success": False,
                    "error": f"缺少布局框: {name}",
                }), 400

        images = image_generator.create_images(
            text=text,
            fields=fields,
            boxes=boxes,
            settings=settings,
        )

        task_id = str(uuid.uuid4())
        preview_urls = []

        for page_index, image in enumerate(images, start=1):
            with tempfile.NamedTemporaryFile(
                prefix=f"handwriter_{task_id}_{page_index}_",
                suffix=".png",
                delete=False,
            ) as f:
                path = f.name

            # Windows 下先关闭 NamedTemporaryFile，再让 Pillow 写入。
            image.save(path, format="PNG")

            image_paths.append(path)
            preview_urls.append(
                "/view_image/" + os.path.basename(path)
            )

        tasks[task_id] = {
            "name": fields.get("姓名", "未知"),
            "patient_id": fields.get("住院号", "未知"),
            "image_paths": image_paths,
            "page_count": len(image_paths),
            "created_at": time.time(),
        }

        write_log(
            "预览图片",
            request.remote_addr,
            f"{task_id} 共{len(images)}页",
        )

        return jsonify({
            "success": True,
            "task_id": task_id,
            "page_count": len(images),
            "preview_urls": preview_urls,
        })

    except Exception as e:
        # 如果生成到一半失败，删除已经创建的临时 PNG。
        for path in image_paths:
            remove_temp_file(path)

        return jsonify({"success": False, "error": str(e)}), 500


# =========================================================
# 查看临时 PNG
# =========================================================

@app.route("/view_image/<filename>")
def view_image(filename):
    safe_filename = os.path.basename(filename)

    if (
        not safe_filename.startswith("handwriter_")
        or not safe_filename.lower().endswith(".png")
    ):
        return "文件不存在", 404

    path = os.path.join(tempfile.gettempdir(), safe_filename)

    if not os.path.isfile(path):
        return "文件不存在", 404

    return send_file(path, mimetype="image/png")


# =========================================================
# 下载已经生成好的 JPG ZIP
# =========================================================

def safe_filename_part(value):
    value = str(value or "未知")

    for ch in '<>:"/\\|?*':
        value = value.replace(ch, "_")

    value = value.strip()
    return value or "未知"


@app.route("/download_images/<task_id>")
def download_generated_images(task_id):
    info = tasks.get(task_id)

    if not info:
        return "任务不存在或已失效", 404

    image_paths = info.get("image_paths", [])

    if not image_paths:
        cleanup_task(task_id)
        return "没有可下载的图片", 404

    name = safe_filename_part(info.get("name", "未知"))
    patient_id = safe_filename_part(info.get("patient_id", "未知"))

    zip_buffer = BytesIO()
    written_count = 0

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for page_index, path in enumerate(image_paths, start=1):
            if not os.path.isfile(path):
                continue

            with Image.open(path) as image:
                if image.mode != "RGB":
                    image = image.convert("RGB")

                jpg_buffer = BytesIO()
                image.save(
                    jpg_buffer,
                    format="JPEG",
                    quality=95,
                )

                jpg_name = f"{name}-{page_index}-{patient_id}.jpg"
                zip_file.writestr(jpg_name, jpg_buffer.getvalue())
                written_count += 1

    if written_count == 0:
        cleanup_task(task_id)
        return "图片文件已失效，请重新生成预览", 404

    zip_buffer.seek(0)
    zip_name = f"{name}-{patient_id}.zip"
    zip_bytes = zip_buffer.getvalue()

    write_log(
        "下载zip图片包",
        request.remote_addr,
        zip_name,
    )

    # ZIP 已经读入内存，可以安全删除本任务临时 PNG。
    cleanup_task(task_id)

    response = make_response(zip_bytes)
    response.headers["Content-Type"] = "application/zip"
    response.headers["Content-Disposition"] = (
        "attachment; filename*=UTF-8''" + quote(zip_name)
    )

    return response


if __name__ == "__main__":
    print("启动手写体文档生成器！！！：http://0.0.0.0:8888")
    app.run(debug=False, host="0.0.0.0", port=8888)
