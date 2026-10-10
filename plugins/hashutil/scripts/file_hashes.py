# 中文注释：本地文件内容哈希锚表节点。
# 输入构念：任意被引擎暂存的文件（FileSet 逐个枚举，AUTONOMICS_INPUT_COUNT 计数）。
# 规则来源：方案 §26.1 运行账本要求输入/输出哈希；引擎 FileRef 对本地文件只记
# size+mtime，因此内容指纹在此显式计算。blake3 与 snapshot_export 的锚表口径一致。
# 失败处理：算法名不合法 → 退出码 2；文件不可读 → Python 异常非零退出，
# 引擎按 MissingOutput 处理。解释边界：只对已暂存字节负责，不追溯文件来源。
import hashlib
import os
import sys
from pathlib import Path

try:
    import blake3 as _blake3
except ImportError:
    _blake3 = None

ALGOS = [a for a in os.environ.get("HASHUTIL_ALGOS", "sha256 blake3").split() if a]
CHUNK = max(1, int(os.environ.get("HASHUTIL_CHUNK_MB", "16"))) * 1024 * 1024
COUNT = int(os.environ.get("AUTONOMICS_INPUT_COUNT", "0"))
OUT_TSV = os.environ["AUTONOMICS_OUTPUT0"]
OUT_LOG = os.environ["AUTONOMICS_OUTPUT1"]

SUPPORTED = {"sha256", "blake3"}
unknown = [a for a in ALGOS if a not in SUPPORTED]
if unknown or not ALGOS:
    print(f"unsupported algos {unknown or '(empty)'}; supported: {sorted(SUPPORTED)}", file=sys.stderr)
    sys.exit(2)
if "blake3" in ALGOS and _blake3 is None:
    print("blake3 requested but blake3 python binding missing in image", file=sys.stderr)
    sys.exit(2)

rows = []
log_lines = []
for i in range(COUNT):
    path = os.environ[f"AUTONOMICS_INPUT{i}"]
    name = Path(path).name
    hashers = {}
    for algo in ALGOS:
        hashers[algo] = _blake3.blake3() if algo == "blake3" else hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            size += len(block)
            for hasher in hashers.values():
                hasher.update(block)
    for algo in ALGOS:
        rows.append((name, algo, hashers[algo].hexdigest(), size))
    log_lines.append(f"hashed\t{name}\t{size}\tbytes\talgos={','.join(ALGOS)}")

with open(OUT_TSV, "w", encoding="utf-8") as tsv:
    tsv.write("file\talgorithm\tdigest\tsize_bytes\n")
    for row in rows:
        tsv.write("\t".join(str(field) for field in row) + "\n")

log_lines.append(f"files={COUNT}\trows={len(rows)}\tdone")
with open(OUT_LOG, "w", encoding="utf-8") as log:
    log.write("\n".join(log_lines) + "\n")
