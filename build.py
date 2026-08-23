import os
import subprocess
import shutil

def clean_previous_builds():
    """清理之前的构建文件"""
    folders_to_remove = ['dist', 'build']
    files_to_remove = ['HandWriter.spec', 'app.spec']
    
    for folder in folders_to_remove:
        if os.path.exists(folder):
            print(f"删除文件夹: {folder}")
            shutil.rmtree(folder)
    
    for file in files_to_remove:
        if os.path.exists(file):
            print(f"删除文件: {file}")
            os.remove(file)

def build_app():
    print("开始打包 HandWriter...")
    print("=" * 50)
    
    # 清理之前的构建
    clean_previous_builds()
    
    # 打包命令
    cmd = [
        'pyinstaller',
        'app.py',
        '--onefile',                    # 单个exe文件
        '--add-data', 'base.jpg;.',     # 包含基础图片
        '--add-data', 'handwrite.ttf;.', # 包含字体文件
        '--add-data', 'index.html;.',   # 包含网页文件
        '--name', 'HandWriter',         # 输出文件名
        '--clean',                      # 清理缓存
        '--noconsole'                   # 不显示控制台窗口
    ]
    
    print("执行打包命令...")
    print(' '.join(cmd))
    print("-" * 50)
    
    # 执行打包
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 检查结果
    if result.returncode == 0:
        print("✅ 打包成功！")
        print("-" * 50)
        
        # 检查生成的文件
        exe_path = os.path.join('dist', 'HandWriter.exe')
        if os.path.exists(exe_path):
            file_size = os.path.getsize(exe_path) / (1024 * 1024)  # MB
            print(f"📁 生成文件: {exe_path}")
            print(f"📊 文件大小: {file_size:.2f} MB")
            print("\n🎉 打包完成！请将 dist/HandWriter.exe 复制到内网电脑使用")
        else:
            print("❌ 错误：EXE文件未生成")
    else:
        print("❌ 打包失败！")
        print("错误信息:")
        print(result.stderr)
        print("输出信息:")
        print(result.stdout)

if __name__ == '__main__':
    build_app()