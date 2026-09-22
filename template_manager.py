import datetime
import json
import os
import re
import uuid

from flask import Blueprint, jsonify, request


def create_template_blueprint(
    get_app_dir,
    write_log
):
    """
    模板功能独立 Blueprint。

    负责：
    - 旧默认 template.json
    - 模板列表
    - 保存模板
    - 加载模板
    - 设置默认模板
    - 删除模板

    app.py 只需要注册这个 Blueprint。
    """

    bp = Blueprint(
        "template_manager",
        __name__
    )

    templates_dir = os.path.join(
        get_app_dir(),
        "templates"
    )

    template_settings_path = os.path.join(
        get_app_dir(),
        "template_settings.json"
    )

    # =====================================================
    # 内部工具
    # =====================================================

    def ensure_templates_dir():

        os.makedirs(
            templates_dir,
            exist_ok=True
        )


    def validate_template_id(
        template_id
    ):

        if not template_id:
            return False

        return bool(
            re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}",
                str(template_id)
            )
        )


    def get_saved_template_path(
        template_id
    ):

        if not validate_template_id(
            template_id
        ):
            raise ValueError(
                "无效模板ID"
            )

        ensure_templates_dir()

        return os.path.join(
            templates_dir,
            template_id + ".json"
        )


    def read_saved_template(
        template_id
    ):

        path = get_saved_template_path(
            template_id
        )

        if not os.path.isfile(
            path
        ):
            return None

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(
                f
            )


    def read_template_settings():

        if not os.path.isfile(
            template_settings_path
        ):

            return {
                "default_template_id":
                    None
            }

        try:

            with open(
                template_settings_path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(
                    f
                )

            if not isinstance(
                data,
                dict
            ):

                return {
                    "default_template_id":
                        None
                }

            return data

        except Exception:

            return {
                "default_template_id":
                    None
            }


    def write_template_settings(
        data
    ):

        temp_path = (
            template_settings_path
            + ".tmp"
        )

        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_path,
            template_settings_path
        )


    def get_default_template_id():

        settings = (
            read_template_settings()
        )

        template_id = (
            settings.get(
                "default_template_id"
            )
        )

        if not validate_template_id(
            template_id
        ):

            return None

        path = get_saved_template_path(
            template_id
        )

        if not os.path.isfile(
            path
        ):

            return None

        return template_id


    # =====================================================
    # 模板列表
    # =====================================================

    @bp.route(
        "/api/templates",
        methods=["GET"]
    )
    def list_saved_templates():

        try:

            ensure_templates_dir()

            items = []

            for filename in os.listdir(
                templates_dir
            ):

                if not filename.lower().endswith(
                    ".json"
                ):

                    continue

                path = os.path.join(
                    templates_dir,
                    filename
                )

                try:

                    with open(
                        path,
                        "r",
                        encoding="utf-8"
                    ) as f:

                        data = json.load(
                            f
                        )

                    template_id = (
                        data.get(
                            "id"
                        )
                        or os.path.splitext(
                            filename
                        )[0]
                    )

                    name = (
                        data.get(
                            "name"
                        )
                        or template_id
                    )

                    items.append({
                        "id":
                            template_id,

                        "name":
                            name,

                        "updated_at":
                            data.get(
                                "updated_at",
                                ""
                            )
                    })

                except Exception:

                    # 单个模板损坏时，
                    # 不影响其他模板显示。
                    continue


            items.sort(
                key=lambda item:
                    (
                        item.get(
                            "updated_at",
                            ""
                        ),

                        item.get(
                            "name",
                            ""
                        )
                    ),

                reverse=True
            )


            return jsonify({
                "success": True,

                "templates":
                    items,

                "default_template_id":
                    get_default_template_id()
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500


    # =====================================================
    # 加载模板
    # =====================================================

    @bp.route(
        "/api/templates/<template_id>",
        methods=["GET"]
    )
    def load_saved_template(
        template_id
    ):

        try:

            data = read_saved_template(
                template_id
            )

            if not data:

                return jsonify({
                    "success": False,
                    "error":
                        "模板不存在"
                }), 404


            return jsonify({
                "success": True,
                "template":
                    data
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 400


    # =====================================================
    # 保存模板
    # =====================================================

    @bp.route(
        "/api/templates",
        methods=["POST"]
    )
    def save_saved_template():

        try:

            data = (
                request.get_json(
                    silent=True
                )
                or {}
            )


            name = str(
                data.get(
                    "name",
                    ""
                )
            ).strip()


            if not name:

                return jsonify({
                    "success": False,
                    "error":
                        "模板名称不能为空"
                }), 400


            template_id = data.get(
                "id"
            )


            if template_id:

                template_id = str(
                    template_id
                )

                if not validate_template_id(
                    template_id
                ):

                    return jsonify({
                        "success": False,
                        "error":
                            "模板ID无效"
                    }), 400

            else:

                template_id = (
                    uuid.uuid4().hex
                )


            old_data = (
                read_saved_template(
                    template_id
                )
                or {}
            )


            now = (
                datetime.datetime.now()
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            template_data = {

                "version": 1,

                "id":
                    template_id,

                "name":
                    name,

                "created_at":
                    old_data.get(
                        "created_at",
                        now
                    ),

                "updated_at":
                    now,

                "fields":
                    data.get(
                        "fields",
                        {}
                    ),

                "settings":
                    data.get(
                        "settings",
                        {}
                    ),

                "boxes":
                    data.get(
                        "boxes",
                        {}
                    ),

                "body_html":
                    str(
                        data.get(
                            "body_html",
                            ""
                        )
                    ),

                "body_text":
                    str(
                        data.get(
                            "body_text",
                            ""
                        )
                    )

            }


            path = get_saved_template_path(
                template_id
            )

            temp_path = (
                path
                + ".tmp"
            )


            with open(
                temp_path,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    template_data,
                    f,
                    ensure_ascii=False,
                    indent=2
                )


            os.replace(
                temp_path,
                path
            )


            write_log(
                "保存模板",
                request.remote_addr,
                name
            )


            return jsonify({
                "success": True,

                "template": {
                    "id":
                        template_id,

                    "name":
                        name,

                    "updated_at":
                        now
                }
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500


    # =====================================================
    # 默认模板
    # =====================================================

    @bp.route(
        "/api/templates/default",
        methods=["POST"]
    )
    def set_default_template():

        try:

            data = (
                request.get_json(
                    silent=True
                )
                or {}
            )


            template_id = str(
                data.get(
                    "id",
                    ""
                )
            ).strip()


            if not validate_template_id(
                template_id
            ):

                return jsonify({
                    "success": False,
                    "error":
                        "模板ID无效"
                }), 400


            template = read_saved_template(
                template_id
            )


            if not template:

                return jsonify({
                    "success": False,
                    "error":
                        "模板不存在"
                }), 404


            settings = (
                read_template_settings()
            )

            settings[
                "default_template_id"
            ] = template_id

            write_template_settings(
                settings
            )


            write_log(
                "设置默认模板",
                request.remote_addr,
                template.get(
                    "name",
                    template_id
                )
            )


            return jsonify({
                "success": True,

                "default_template_id":
                    template_id
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500


    # =====================================================
    # 删除模板
    # =====================================================

    @bp.route(
        "/api/templates/<template_id>",
        methods=["DELETE"]
    )
    def delete_saved_template(
        template_id
    ):

        try:

            if not validate_template_id(
                template_id
            ):

                return jsonify({
                    "success": False,
                    "error":
                        "模板ID无效"
                }), 400


            template = read_saved_template(
                template_id
            )


            if not template:

                return jsonify({
                    "success": False,
                    "error":
                        "模板不存在"
                }), 404


            path = get_saved_template_path(
                template_id
            )

            os.remove(
                path
            )


            settings = (
                read_template_settings()
            )


            if (
                settings.get(
                    "default_template_id"
                )
                == template_id
            ):

                settings[
                    "default_template_id"
                ] = None

                write_template_settings(
                    settings
                )


            write_log(
                "删除模板",
                request.remote_addr,
                template.get(
                    "name",
                    template_id
                )
            )


            return jsonify({
                "success": True,

                "deleted_id":
                    template_id
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500


    # =====================================================
    # 原来的 template.json 基础内容
    # =====================================================

    @bp.route(
        "/template",
        methods=["GET"]
    )
    def get_legacy_template():

        try:

            path = os.path.join(
                get_app_dir(),
                "template.json"
            )


            if not os.path.exists(
                path
            ):

                return jsonify({
                    "success": True,
                    "text": "",
                    "病区": "",
                    "姓名": "",
                    "床号": "",
                    "住院号": ""
                })


            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(
                    f
                )


            return jsonify({
                "success": True,
                **data
            })


        except Exception as e:

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500


    return bp
