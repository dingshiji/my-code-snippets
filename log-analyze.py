from typing import List, Tuple

# === 参数 ===
input_file = "app.log"          # 原始日志文件
output_file = "excerpts.log"    # 提取后的新文件
date_prefix = "2025-09-05"      # 仅保留不是这个前缀开头的片段 + 上下文日期日志
ctx_before = 3                  # 每个异常片段前，保留的“日期开头”正常日志条数
ctx_after = 3                   # 每个异常片段后，保留的“日期开头”正常日志条数
add_divider = True             # 片段之间是否插入分隔线，便于阅读

# === 工具函数 ===
def is_date_line(line: str, prefix: str) -> bool:
    # 严格以指定日期起始，例如 "2025-09-05 04:00:01 ..."
    return line.startswith(prefix)

def group_contiguous(indices: List[int]) -> List[Tuple[int, int]]:
    """把连续索引合并成区间 [start, end]（含端点）"""
    if not indices:
        return []
    indices.sort()
    ranges = []
    s = e = indices[0]
    for i in indices[1:]:
        if i == e + 1:
            e = i
        else:
            ranges.append((s, e))
            s = e = i
    ranges.append((s, e))
    return ranges

def collect_context_indices(lines: List[str], start: int, end: int,
                            prefix: str, n_before: int, n_after: int) -> Tuple[List[int], List[int]]:
    """围绕异常区间[start, end]，向前/向后各收集至多 n_before / n_after 条“日期开头”行的索引"""
    before_idx = []
    i = start - 1
    while i >= 0 and len(before_idx) < n_before:
        if is_date_line(lines[i], prefix):
            before_idx.append(i)
        i -= 1
    before_idx.reverse()

    after_idx = []
    j = end + 1
    while j < len(lines) and len(after_idx) < n_after:
        if is_date_line(lines[j], prefix):
            after_idx.append(j)
        j += 1

    return before_idx, after_idx

# === 主逻辑 ===
with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
    all_lines = f.readlines()

# 1) 找出所有“不以指定日期开头”的行索引
non_date_indices = [i for i, line in enumerate(all_lines) if not is_date_line(line, date_prefix)]

# 2) 合并为连续异常区间
blocks = group_contiguous(non_date_indices)

# 3) 对每个异常区间，收集上下文日期行，并合并最终输出索引集合
to_write_indices = set()
segments = []  # 保存每个片段的完整索引列表（便于插入分隔线）

for (s, e) in blocks:
    before_idx, after_idx = collect_context_indices(all_lines, s, e, date_prefix, ctx_before, ctx_after)
    segment_indices = before_idx + list(range(s, e + 1)) + after_idx
    for k in segment_indices:
        to_write_indices.add(k)
    segments.append(segment_indices)

# 4) 为了确保原始顺序写出，同时可选插入分隔线
with open(output_file, "w", encoding="utf-8") as out:
    if add_divider:
        for seg_no, seg in enumerate(segments, 1):
            out.write(f"----- SEGMENT {seg_no} START -----\n")
            for idx in seg:
                out.write(all_lines[idx])
            out.write(f"----- SEGMENT {seg_no} END -----\n")
    else:
        # 无分隔线：仅按原顺序写出被选中的行
        for i, line in enumerate(all_lines):
            if i in to_write_indices:
                out.write(line)

print(f"提取完成，共生成 {len(segments)} 个异常片段，上下文各保留 {ctx_before}/{ctx_after} 条。输出文件：{output_file}")
