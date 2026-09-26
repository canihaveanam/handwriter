import os
import sys
import shutil
import subprocess


def clean_previous_builds():
    """清理之前的构建文件"""

    folders_to_remove = [
        "dist",
        "build"
    ]

    files_to_remove = [
        "HandWriter.spec",
        "app.spec"
    ]

    for folder in folders_to_remove:
        if os.path.exists(folder):
            print(f"删除文件夹: {folder}")
            shutil.rmtree(folder, ignore_errors=True)

    for file in files_to_remove:
        if os.path.exists(file):
            print(f"删除文件: {file}")
            os.remove(file)


def build_app():

    print("开始打包 HandWriter...")
    print("=" * 60)

    # 当前 build.py 所在目录
    project_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    # 切换到项目根目录
    os.chdir(project_dir)

    print(f"项目目录: {project_dir}")
    print(f"Python: {sys.executable}")
    print("-" * 60)


    # 检查必要文件

    required_files = [
    "app.py",
    "base.jpg",
    "index.html",
    "template_settings.json",
    "font_manager.py",
    "image_generator.py",
    "template_manager.py",
    ]

    required_dirs = [
    "fonts",
    "templates",
    ]


    missing = []

    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)

    for folder in required_dirs:
        if not os.path.isdir(folder):
            missing.append(folder + "/")


    if missing:

        print("❌ 缺少以下文件/目录:")

        for item in missing:
            print("   -", item)

        return


    # 检查字体

    print("发现字体:")

    fonts = []

    for filename in os.listdir("fonts"):

        if filename.lower().endswith(
            (".ttf", ".otf")
        ):
            fonts.append(filename)
            print(
                f"   ✓ fonts/{filename}"
            )


    if not fonts:

        print("❌ fonts 文件夹没有字体")

        return


    print("-" * 60)


    # 清理旧版本

    clean_previous_builds()


    # PyInstaller命令

    cmd = [
    sys.executable,
    "-m",
    "PyInstaller",

    "app.py",

    # 先用 onedir，打包快、启动快、方便排错
    "--onedir",

    "--name",
    "HandWriter",

    # 前端
    "--add-data",
    "index.html;.",

    # 底图
    "--add-data",
    "base.jpg;.",

    # 字体
    "--add-data",
    "fonts;fonts",

    # 模板
    "--add-data",
    "templates;templates",

    # 模板配置
    "--add-data",
    "template_settings.json;.",

    "--clean",
    "--noconfirm",
    # 不显示黑色终端
    "--noconsole",
    ]


    print("执行打包命令:")
    print()

    print(
        " ".join(cmd)
    )

    print()

    print("-" * 60)


    # 执行

    result = subprocess.run(cmd)


    print("-" * 60)


    if result.returncode == 0:


        exe_path = os.path.join(
            "dist",
            "HandWriter",
            "HandWriter.exe"
        )


        if os.path.exists(exe_path):

            size = (
                os.path.getsize(exe_path)
                /
                (1024 * 1024)
            )


            print()
            print("✅ 打包成功！")

            print(
                f"📁 EXE位置:"
                f" {os.path.abspath(exe_path)}"
            )

            print(
                f"📊 文件大小:"
                f" {size:.2f} MB"
            )

            print()

            print(
                "🎉 完成"
            )


        else:

            print(
                "❌ 没找到 HandWriter.exe"
            )


    else:

        print()

        print(
            "❌ PyInstaller 打包失败"
        )

        print(
            f"返回代码: {result.returncode}"
        )



if __name__ == "__main__":

    build_app()