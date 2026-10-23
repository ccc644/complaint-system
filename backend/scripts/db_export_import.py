# -*- coding: utf-8 -*-
"""数据库导出 / 导入一体脚本（封装 pg_dump / pg_restore，Windows / Linux 通用）

用法（在任意目录均可，备份路径相对当前目录）：
    python db_export_import.py export [备份文件路径]
        省略路径 -> backup/库名_年月日_时分秒.dump
    python db_export_import.py import <备份文件路径> [--yes]
        --yes 跳过交互确认（脚本化用，慎用）

两种模式（由配置区 DOCKER_CONTAINER 决定）：
    - 本机模式（默认）：在宿主机上执行 pg_dump / pg_restore，经 host:port 连 PG。
      PG 用 Docker 部署但映射了端口（如 -p 5432:5432）的同样适用。
    - Docker 模式：docker exec 进 PG 容器内执行，docker cp 搬运备份文件。
      宿主机无需安装 PG 工具、无需端口映射，且工具版本必然与服务端一致。

说明 / 限制：
    - 仅支持 pg_dump 自定义格式（-F c，.dump 文件）；纯文本 .sql 不支持，会明确报错
    - 导入使用 --clean --if-exists --no-owner：先删除目标库现有对象再重建，
      现有数据被覆盖；--no-owner 让对象归属导入时使用的账号（跨账号迁移不受源账号影响）
    - 目标库需已存在（脚本不自动建库；全新环境先 createdb 或由后端 init_db 建库）
    - 密码通过 PGPASSWORD 环境变量传给子进程，不出现在命令行
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ══════════════════ 配置区（按需修改） ══════════════════

# 数据库连接（Docker 模式不使用 HOST/PORT，容器内走本地 socket）
DB_NAME = "complaint_db"
DB_USER = "complaint"
DB_PASSWORD = ""  # <-- 在这里填密码（留空则本机模式会提示必填）
DB_HOST = "127.0.0.1"
DB_PORT = 5432

# Docker 模式：填 PG 容器名（docker ps 的 NAMES 列，compose 形如 xxx-db-1）
#   ""     = 本机模式（默认）
#   "auto" = 自动探测正在运行的 postgres 容器（多个时会列出来让你手动填）
DOCKER_CONTAINER = ""

# 本机模式：pg 工具目录（含 pg_dump / pg_restore），留空自动找
# 查找顺序：此处配置 -> 系统 PATH -> 常见安装位置（取版本最高的一个）
PG_BIN_DIR = ""

# ══════════════════ 以下为实现，一般不用动 ══════════════════

WIN_BIN_GLOBS = [
    r"C:\Program Files\PostgreSQL\*\bin",
    r"C:\Program Files (x86)\PostgreSQL\*\bin",
    r"D:\Program Files\PostgreSQL\*\bin",
]
LINUX_BIN_GLOBS = [
    "/usr/lib/postgresql/*/bin",
    "/usr/pgsql-*/bin",
    "/usr/local/pgsql/bin",
]

DUMP_MAGIC = b"PGDMP"  # pg_dump 自定义格式文件头，导入前校验

# 控制台中文输出兜底（非 UTF-8 终端用替换字符，避免直接报错）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass


def run(cmd, env=None):
    """执行子进程，失败时打印命令与 stderr 后退出。"""
    proc = subprocess.run([str(c) for c in cmd], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        print(f"\n[失败] {' '.join(str(c) for c in cmd)}")
        if out:
            print(out)
        if err:
            print(err)
        sys.exit(1)
    return out


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _ver_key(path):
    """从安装路径提取 PG 大版本，仅用于多个候选里优先选版本最高的客户端。"""
    for pat in (r"[Pp]ostgreSQL[/\\](\d+)", r"pgsql-(\d+)"):
        m = re.search(pat, str(path))
        if m:
            return int(m.group(1))
    return 0


def find_pg_tool(name):
    """定位本机 pg_dump / pg_restore：配置目录 -> PATH -> 常见安装位置。"""
    exe = f"{name}.exe" if os.name == "nt" else name
    if PG_BIN_DIR:
        p = Path(PG_BIN_DIR) / exe
        if p.is_file():
            return str(p)
        sys.exit(f"[错误] PG_BIN_DIR 中找不到 {p}（检查配置区路径）")
    found = shutil.which(name)
    if found:
        return found
    globs = WIN_BIN_GLOBS if os.name == "nt" else LINUX_BIN_GLOBS
    hits = [h for g in globs for h in glob.glob(str(Path(g) / exe))]
    if not hits:
        sys.exit(
            "[错误] 未找到 pg 工具。解决办法（任选其一）：\n"
            f"  1. 在脚本配置区 PG_BIN_DIR 填 pg 工具目录（含 {exe}）；\n"
            "  2. 把 PG 的 bin 目录加入系统 PATH；\n"
            "  3. PG 用 Docker 部署时，配置区 DOCKER_CONTAINER 填容器名，改用 Docker 模式。"
        )
    return max(hits, key=_ver_key)


def find_docker():
    d = shutil.which("docker")
    if not d:
        sys.exit("[错误] 未找到 docker 命令（确认 Docker 已安装且在 PATH 中）")
    return d


def resolve_container(docker):
    """解析 PG 容器名：DOCKER_CONTAINER 为 "auto" 时探测正在运行的 postgres 容器。"""
    if DOCKER_CONTAINER != "auto":
        return DOCKER_CONTAINER
    out = run([docker, "ps", "--format", "{{.Names}}\t{{.Image}}"])
    cands = [ln.split("\t")[0] for ln in out.splitlines()
             if "\t" in ln and "postgres" in ln.split("\t")[1].lower()]
    if len(cands) == 1:
        print(f"[预检] 自动探测到 PG 容器：{cands[0]}")
        return cands[0]
    if not cands:
        sys.exit('[错误] DOCKER_CONTAINER="auto" 未发现正在运行的 postgres 容器，请在配置区手动填容器名')
    sys.exit("[错误] 发现多个 postgres 容器，请在配置区 DOCKER_CONTAINER 明确填写其一：\n  "
             + "\n  ".join(cands))


def docker_tool_check(docker, container, tool):
    """容器内工具连通性预检，顺带打印版本。"""
    print(f"[预检] {tool}（容器 {container}）: {run([docker, 'exec', container, tool, '--version'])}")


def warn_empty_password():
    print("[提示] DB_PASSWORD 为空：容器内本地 socket 连接通常免密；"
          "若后面报密码错误，请在配置区填写 DB_PASSWORD")


def cmd_export(args):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.file) if args.file else Path("backup") / f"{DB_NAME}_{ts}.dump"
    if out_path.suffix == "":
        out_path = out_path.with_suffix(".dump")
    if out_path.exists():
        sys.exit(f"[错误] 备份文件已存在，不覆盖：{out_path.resolve()}\n"
                 "（换一个文件名，或确认旧文件可删后手动删除再执行）")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if DOCKER_CONTAINER:
        docker = find_docker()
        container = resolve_container(docker)
        docker_tool_check(docker, container, "pg_dump")
        if not DB_PASSWORD:
            warn_empty_password()
        tmp = f"/tmp/{out_path.name}"
        print(f"[1/3] 容器内导出 -> {tmp}")
        run([docker, "exec", "-e", f"PGPASSWORD={DB_PASSWORD}", container,
             "pg_dump", "-w", "-U", DB_USER, "-d", DB_NAME, "-F", "c", "-f", tmp])
        print(f"[2/3] docker cp -> {out_path}")
        run([docker, "cp", f"{container}:{tmp}", out_path])
        print("[3/3] 清理容器内临时文件")
        run([docker, "exec", container, "rm", "-f", tmp])
    else:
        if not DB_PASSWORD:
            sys.exit("[错误] 本机模式必须在配置区填写 DB_PASSWORD")
        pg_dump = find_pg_tool("pg_dump")
        print(f"[预检] {run([pg_dump, '--version'])}")
        print(f"[1/1] pg_dump 导出 -> {out_path}")
        env = {**os.environ, "PGPASSWORD": DB_PASSWORD}
        run([pg_dump, "-w", "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER,
             "-d", DB_NAME, "-F", "c", "-f", out_path], env=env)

    size = out_path.stat().st_size
    if size == 0:
        sys.exit("[错误] 导出文件为空，请检查上面的报错")
    print(f"\n[完成] {out_path.resolve()}（{human_size(size)}）")
    print("提示：备份文件建议转存到服务器以外的存储位置（见运维手册 §10.3）。")


def cmd_import(args):
    path = Path(args.file)
    if not path.is_file():
        sys.exit(f"[错误] 备份文件不存在：{path}")
    if path.suffix.lower() == ".sql":
        sys.exit("[错误] 纯文本 .sql 备份不支持（需 psql 执行）。请使用自定义格式（-F c / .dump）的备份。")
    with open(path, "rb") as f:
        if f.read(len(DUMP_MAGIC)) != DUMP_MAGIC:
            sys.exit("[错误] 该文件不是 pg_dump 自定义格式（-F c）备份（文件头校验不符）")

    if DOCKER_CONTAINER:
        docker = find_docker()
        container = resolve_container(docker)
        docker_tool_check(docker, container, "pg_restore")
        if not DB_PASSWORD:
            warn_empty_password()
        target = f"Docker 容器 {container}"
        restore_cmd = ["docker", "exec", "-e", f"PGPASSWORD={DB_PASSWORD}", container,
                       "pg_restore", "-w", "-U", DB_USER, "-d", DB_NAME,
                       "--clean", "--if-exists", "--no-owner", f"/tmp/{path.name}"]
        pre_cmds = [["docker", "cp", path, f"{container}:/tmp/{path.name}"]]
        post_cmds = [["docker", "exec", container, "rm", "-f", f"/tmp/{path.name}"]]
        env = None
    else:
        if not DB_PASSWORD:
            sys.exit("[错误] 本机模式必须在配置区填写 DB_PASSWORD")
        pg_restore = find_pg_tool("pg_restore")
        print(f"[预检] {run([pg_restore, '--version'])}")
        print("[提示] pg_restore 大版本应不低于服务端大版本，否则可能报格式不兼容")
        target = f"本机 {DB_HOST}:{DB_PORT}"
        restore_cmd = [pg_restore, "-w", "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER,
                       "-d", DB_NAME, "--clean", "--if-exists", "--no-owner", path]
        pre_cmds = []
        post_cmds = []
        env = {**os.environ, "PGPASSWORD": DB_PASSWORD}

    st = path.stat()
    print("\n即将恢复（覆盖）数据库：")
    print(f"    目标   : {target} -> 库 {DB_NAME}（账号 {DB_USER}）")
    print(f"    备份   : {path.resolve()}（{human_size(st.st_size)}，"
          f"{datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M}）")
    print("    [!] 导入会先删除目标库现有对象再重建，现有数据全部被覆盖")
    print("    [!] 请先停止后端服务（uvicorn / start.bat），避免恢复期间产生写入")
    if not args.yes and input("输入 yes 确认继续（其他任意输入取消）: ").strip().lower() != "yes":
        sys.exit("已取消。")

    for i, cmd in enumerate([*pre_cmds, restore_cmd, *post_cmds], 1):
        total = len(pre_cmds) + 1 + len(post_cmds)
        print(f"[{i}/{total}] {' '.join(str(c) for c in cmd)}")
        run(cmd, env=env)

    print("\n[完成] 恢复完毕。请启动后端服务并抽查数据（登录、看板、工单列表）。")


def main():
    ap = argparse.ArgumentParser(
        description="客诉系统 PostgreSQL 导出/导入脚本（本机 PG 与 Docker 部署通用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python db_export_import.py export\n"
               "  python db_export_import.py export D:/backup/complaints.dump\n"
               "  python db_export_import.py import backup/complaint_db_20260902_120000.dump")
    sub = ap.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export", help="导出数据库（pg_dump 自定义格式）")
    p_export.add_argument("file", nargs="?", help="备份文件路径（默认 backup/库名_时间戳.dump）")
    p_import = sub.add_parser("import", help="导入备份（pg_restore，覆盖目标库，需确认）")
    p_import.add_argument("file", help="备份文件路径（.dump）")
    p_import.add_argument("--yes", action="store_true", help="跳过交互确认（脚本化用，慎用）")
    args = ap.parse_args()

    if args.command == "export":
        cmd_export(args)
    else:
        cmd_import(args)


if __name__ == "__main__":
    main()
