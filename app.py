import atexit
import datetime
import gc
import os
import sys
import tempfile
import time
import traceback
import uuid
import zipfile

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)
from PIL import Image, UnidentifiedImageError

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

# Flask 整个请求的上限略高于单张背景 15MB，给 multipart 边界留空间。
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

font_manager = FontManager(
    get_resource_path,
    fonts_dir="fonts",
    default_font="StyleA",
)

DEFAULT_BACKGROUND_PATH = get_resource_path("base.jpg")
image_generator = ImageGenerator(
    font_manager,
    DEFAULT_BACKGROUND_PATH,
)

# 自定义背景限制。
MAX_BACKGROUND_FILE_BYTES = 15 * 1024 * 1024
MAX_BACKGROUND_SIDE = 12000
MAX_BACKGROUND_PIXELS = 100_000_000
BACKGROUND_TTL_SECONDS = 60 * 60


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
# 临时图片任务 / 临时背景
# =========================================================

tasks = {}
backgrounds = {}

# 只预览不下载时，临时文件最多保存 1 小时。
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

    # 原代码记录了 zip_path，但没有清理；这里一起修掉。
    remove_temp_file(info.get("zip_path"))


def cleanup_background(background_id):
    info = backgrounds.pop(background_id, None)
    if not info:
        return
    remove_temp_file(info.get("path"))


def cleanup_expired_tasks():
    now = time.time()

    expired_tasks = []
    for task_id, info in list(tasks.items()):
        created_at = info.get("created_at", 0)
        if now - created_at >= TEMP_TASK_TTL_SECONDS:
            expired_tasks.append(task_id)

    for task_id in expired_tasks:
        cleanup_task(task_id)

    expired_backgrounds = []
    for background_id, info in list(backgrounds.items()):
        created_at = info.get("created_at", 0)
        if now - created_at >= BACKGROUND_TTL_SECONDS:
            expired_backgrounds.append(background_id)

    for background_id in expired_backgrounds:
        cleanup_background(background_id)


def cleanup_all_tasks():
    for task_id in list(tasks.keys()):
        cleanup_task(task_id)

    for background_id in list(backgrounds.keys()):
        cleanup_background(background_id)


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
        DEFAULT_BACKGROUND_PATH,
        mimetype="image/jpeg",
    )


# =========================================================
# 自定义背景
# =========================================================

def get_default_background_size():
    with Image.open(DEFAULT_BACKGROUND_PATH) as image:
        return image.size


def prepare_uploaded_background(uploaded_file, output_path):
    """
    第一版策略：
    - 仅接受 JPG/JPEG/PNG；
    - 解码后转 RGB；
    - 统一 resize 为 base.jpg 的精确尺寸；
    - 保存为高质量 JPEG。

    这样前端现有 boxes 坐标体系无需改变。
    """
    try:
        uploaded_file.stream.seek(0)
        with Image.open(uploaded_file.stream) as source:
            source.load()

            width, height = source.size
            if width < 1 or height < 1:
                raise ValueError("背景图片尺寸无效")

            if width > MAX_BACKGROUND_SIDE or height > MAX_BACKGROUND_SIDE:
                raise ValueError(
                    f"背景图片尺寸过大，单边不能超过 {MAX_BACKGROUND_SIDE}px"
                )

            if width * height > MAX_BACKGROUND_PIXELS:
                raise ValueError("背景图片像素总量过大")

            target_size = get_default_background_size()
            image = source.convert("RGB")

            try:
                if image.size != target_size:
                    try:
                        resample = Image.Resampling.LANCZOS
                    except AttributeError:
                        resample = Image.LANCZOS

                    resized = image.resize(target_size, resample=resample)
                    image.close()
                    image = resized

                image.save(
                    output_path,
                    format="JPEG",
                    quality=95,
                    subsampling=0,
                )
            finally:
                image.close()

            return target_size

    except UnidentifiedImageError:
        raise ValueError("无法识别图片，请上传有效的 JPG、JPEG 或 PNG")


@app.route("/upload_background", methods=["POST"])
def upload_background():
    output_path = None

    try:
        uploaded_file = request.files.get("background")
        if uploaded_file is None or not uploaded_file.filename:
            return jsonify({
                "success": False,
                "error": "请选择背景图片",
            }), 400

        filename = uploaded_file.filename
        extension = os.path.splitext(filename)[1].lower()
        if extension not in {".jpg", ".jpeg", ".png"}:
            return jsonify({
                "success": False,
                "error": "背景只支持 JPG、JPEG、PNG",
            }), 400

        # content_length 对 multipart 单文件不一定总是存在，所以这里只作为额外检查。
        if uploaded_file.content_length and uploaded_file.content_length > MAX_BACKGROUND_FILE_BYTES:
            return jsonify({
                "success": False,
                "error": "背景图片不能超过 15 MB",
            }), 413

        background_id = str(uuid.uuid4())
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"handwriter_bg_{background_id}.jpg",
        )

        width, height = prepare_uploaded_background(
            uploaded_file,
            output_path,
        )

        backgrounds[background_id] = {
            "path": output_path,
            "created_at": time.time(),
            "original_name": filename,
        }

        write_log(
            "上传自定义背景",
            request.remote_addr,
            filename,
        )

        return jsonify({
            "success": True,
            "background_id": background_id,
            "preview_url": f"/view_background/{background_id}",
            "width": width,
            "height": height,
        })

    except ValueError as e:
        remove_temp_file(output_path)
        return jsonify({
            "success": False,
            "error": str(e),
        }), 400

    except Exception as e:
        remove_temp_file(output_path)
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app.route("/view_background/<background_id>")
def view_background(background_id):
    info = backgrounds.get(background_id)
    if not info:
        return "背景不存在或已失效", 404

    path = info.get("path")
    if not path or not os.path.isfile(path):
        cleanup_background(background_id)
        return "背景不存在或已失效", 404

    return send_file(path, mimetype="image/jpeg")


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
    start_time = time.time()

    try:
        print("========== /preview_image START ==========", flush=True)

        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        fields = data.get("fields", {})
        boxes = data.get("boxes", {})
        settings = data.get("settings", {})
        background_id = data.get("background_id")

        print(
            f"[preview] JSON读取完成，正文长度={len(text)}，"
            f"耗时={time.time() - start_time:.2f}s",
            flush=True,
        )

        required_boxes = ["病区", "姓名", "床号", "住院号", "正文"]
        for name in required_boxes:
            if name not in boxes:
                return jsonify({
                    "success": False,
                    "error": f"缺少布局框: {name}",
                }), 400

        # 每次请求显式确定背景。自定义背景使用独立 ImageGenerator，
        # 避免修改全局 image_generator 后出现多用户串背景。
        active_background_path = DEFAULT_BACKGROUND_PATH
        active_generator = image_generator

        if background_id:
            background_info = backgrounds.get(background_id)
            if not background_info:
                return jsonify({
                    "success": False,
                    "error": "自定义背景已失效，请重新上传",
                }), 400

            background_path = background_info.get("path")
            if not background_path or not os.path.isfile(background_path):
                cleanup_background(background_id)
                return jsonify({
                    "success": False,
                    "error": "自定义背景已失效，请重新上传",
                }), 400

            active_background_path = background_path
            active_generator = ImageGenerator(
                font_manager,
                active_background_path,
            )

        task_id = str(uuid.uuid4())
        preview_urls = []
        page_count = 0

        print(f"[preview] task_id={task_id}", flush=True)
        print(
            f"[preview] 背景={'自定义' if background_id else '默认'}: "
            f"{active_background_path}",
            flush=True,
        )
        print("[preview] 准备调用 image_generator.iter_images", flush=True)

        image_iterator = active_generator.iter_images(
            text=text,
            fields=fields,
            boxes=boxes,
            settings=settings,
        )

        for page_index, image in enumerate(image_iterator, start=1):
            page_count = page_index

            print(
                f"[preview] 获得第{page_index}页，"
                f"size={image.size}, mode={image.mode}, "
                f"当前耗时={time.time() - start_time:.2f}s",
                flush=True,
            )

            path = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=f"handwriter_{task_id}_{page_index}_",
                    suffix=".jpg",
                    delete=False,
                ) as f:
                    path = f.name

                image_paths.append(path)

                save_start = time.time()
                image.save(
                    path,
                    format="JPEG",
                    quality=95,
                    subsampling=0,
                )

                print(
                    f"[preview] 第{page_index}页JPG保存完成，"
                    f"保存耗时={time.time() - save_start:.2f}s",
                    flush=True,
                )

                preview_urls.append(
                    "/view_image/" + os.path.basename(path)
                )

            finally:
                try:
                    image.close()
                except Exception:
                    pass
                del image

            gc.collect()

        if page_count == 0:
            raise RuntimeError("没有生成任何预览图片")

        tasks[task_id] = {
            "name": fields.get("姓名", "未知"),
            "patient_id": fields.get("住院号", "未知"),
            "image_paths": image_paths,
            "page_count": page_count,
            "background_id": background_id,
            "created_at": time.time(),
        }

        write_log(
            "预览图片",
            request.remote_addr,
            f"{task_id} 共{page_count}页",
        )

        total_time = time.time() - start_time
        print(
            f"========== /preview_image SUCCESS 共{page_count}页，"
            f"总耗时={total_time:.2f}s ==========",
            flush=True,
        )

        return jsonify({
            "success": True,
            "task_id": task_id,
            "page_count": page_count,
            "preview_urls": preview_urls,
        })

    except Exception as e:
        print("========== /preview_image ERROR ==========", flush=True)
        print(repr(e), flush=True)
        traceback.print_exc()

        for path in image_paths:
            try:
                remove_temp_file(path)
            except Exception as cleanup_error:
                print(
                    f"[preview] 删除临时文件失败 {path}: {cleanup_error}",
                    flush=True,
                )

        gc.collect()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================================================
# 查看临时 JPG
# =========================================================

@app.route("/view_image/<filename>")
def view_image(filename):
    safe_filename = os.path.basename(filename)

    if (
        not safe_filename.startswith("handwriter_")
        or not safe_filename.lower().endswith((".jpg", ".jpeg"))
    ):
        return "文件不存在", 404

    path = os.path.join(tempfile.gettempdir(), safe_filename)
    if not os.path.isfile(path):
        return "文件不存在", 404

    return send_file(path, mimetype="image/jpeg")


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
    zip_name = f"{name}-{patient_id}.zip"

    zip_path = os.path.join(
        tempfile.gettempdir(),
        f"handwriter_{task_id}.zip",
    )

    remove_temp_file(zip_path)

    written_count = 0

    try:
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as zip_file:
            for page_index, path in enumerate(image_paths, start=1):
                if not os.path.isfile(path):
                    continue

                jpg_name = f"{name}-{page_index}-{patient_id}.jpg"
                zip_file.write(path, arcname=jpg_name)
                written_count += 1

        if written_count == 0:
            remove_temp_file(zip_path)
            cleanup_task(task_id)
            return "图片文件已失效，请重新生成预览", 404

        info["zip_path"] = zip_path

        write_log(
            "下载zip图片包",
            request.remote_addr,
            zip_name,
        )

        return send_file(
            zip_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    except Exception:
        remove_temp_file(zip_path)
        raise


if __name__ == "__main__":
    print("启动手写体文档生成器！！！：http://0.0.0.0:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
