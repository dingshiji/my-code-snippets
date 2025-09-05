from typing import List, Tuple, Dict, Any, Optional
import json
import re

# === 参数 ===
input_file = "app.log"            # 原始日志文件
output_file = "excerpts.log"      # 提取后的纯文本文件（含分隔线）
jsonl_file = "excerpts.jsonl"     # 结构化结果（每行一个 JSON 对象）
date_prefix = "2025-09-05"        # 仅保留不是这个前缀开头的片段 + 上下文日期日志
ctx_before = 3                    # 每个异常片段前，保留的“日期开头”正常日志条数
ctx_after = 3                     # 每个异常片段后，保留的“日期开头”正常日志条数
add_divider = True                # 片段之间是否插入分隔线，便于阅读

# 匹配形如 "YYYY-MM-DD HH:MM:SS" 的时间戳
TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})')

# === 工具函数 ===
def is_date_line(line: str, prefix: str) -> bool:
    # 严格以指定日期起始，例如 "2025-09-05 04:00:01 ..."
    return line.startswith(prefix)

def extract_timestamp(line: str) -> Optional[str]:
    """从一行中提取形如 'YYYY-MM-DD HH:MM:SS' 的时间戳"""
    m = TS_RE.match(line)
    return m.group(1) if m else None

def group_contiguous(indices: List[int]) -> List[Tuple[int, int]]:
    """把连续索引合并成区间 [start, end]（含端点）"""
    if not indices:
        return []
    indices.sort()
    ranges: List[Tuple[int, int]] = []
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
    before_idx: List[int] = []
    i = start - 1
    while i >= 0 and len(before_idx) < n_before:
        if is_date_line(lines[i], prefix):
            before_idx.append(i)
        i -= 1
    before_idx.reverse()

    after_idx: List[int] = []
    j = end + 1
    while j < len(lines) and len(after_idx) < n_after:
        if is_date_line(lines[j], prefix):
            after_idx.append(j)
        j += 1
    return before_idx, after_idx

def nearest_prev_date_line(lines: List[str], idx: int, prefix: str) -> Optional[int]:
    """在 idx 之前寻找最近的“日期开头”行索引"""
    i = idx - 1
    while i >= 0:
        if is_date_line(lines[i], prefix):
            return i
        i -= 1
    return None

def nearest_next_date_line(lines: List[str], idx: int, prefix: str) -> Optional[int]:
    """在 idx 之后寻找最近的“日期开头”行索引"""
    j = idx + 1
    while j < len(lines):
        if is_date_line(lines[j], prefix):
            return j
        j += 1
    return None

def first_non_date_in_range(lines: List[str], start: int, end: int, prefix: str) -> Optional[int]:
    """返回 [start, end] 范围内第一行非日期开头的行索引"""
    for k in range(start, end + 1):
        if not is_date_line(lines[k], prefix):
            return k
    return None

def non_date_lines_in_range(lines: List[str], start: int, end: int, prefix: str) -> List[str]:
    """返回 [start, end] 范围内的所有非日期行（保持顺序，原样文本）"""
    out = []
    for k in range(start, end + 1):
        if not is_date_line(lines[k], prefix):
            out.append(lines[k].rstrip("\n"))
    return out

def prefix_before_colon(s: str) -> Optional[str]:
    """取字符串第一个冒号之前的内容；没有冒号返回 None"""
    pos = s.find(":")
    if pos == -1:
        return None
    return s[:pos].strip()

# === 主逻辑 ===
with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
    all_lines = f.readlines()

# 1) 找出所有“不以指定日期开头”的行索引
non_date_indices = [i for i, line in enumerate(all_lines) if not is_date_line(line, date_prefix)]

# 2) 合并为连续异常区间
blocks = group_contiguous(non_date_indices)

# 3) 结构化提取 + 文本输出
segments_info: List[Dict[str, Any]] = []
segments_indices: List[List[int]] = []  # 用于纯文本输出时插入分隔线

with open(output_file, "w", encoding="utf-8") as out, open(jsonl_file, "w", encoding="utf-8") as jout:
    for seg_no, (s, e) in enumerate(blocks, 1):
        # 上下文日期行索引
        before_idx, after_idx = collect_context_indices(all_lines, s, e, date_prefix, ctx_before, ctx_after)

        # 决定“发生时间”：优先用异常区间前最近的日期行；若没有，则用后最近的日期行；再不行为 None
        prev_idx = nearest_prev_date_line(all_lines, s, date_prefix)
        next_idx = nearest_next_date_line(all_lines, e, date_prefix)
        occur_source_idx = prev_idx if prev_idx is not None else next_idx
        occur_source_line = all_lines[occur_source_idx].rstrip("\n") if occur_source_idx is not None else None
        occur_time = extract_timestamp(occur_source_line) if occur_source_line else None

        # 异常第一行（区间内第一行非日期行）
        first_exc_idx = first_non_date_in_range(all_lines, s, e, date_prefix)
        exception_first_line = all_lines[first_exc_idx].rstrip("\n") if first_exc_idx is not None else None
        exception_first_line_prefix = prefix_before_colon(exception_first_line) if exception_first_line else None

        # 异常片段（所有非日期行）
        exception_lines = non_date_lines_in_range(all_lines, s, e, date_prefix)

        # 结构化对象
        obj = {
            "segment_no": seg_no,
            "context_before": [all_lines[i].rstrip("\n") for i in before_idx],
            "context_after": [all_lines[i].rstrip("\n") for i in after_idx],
            "occur_time": occur_time,
            "occur_time_source": occur_source_line,
            "exception_first_line": exception_first_line,
            "exception_first_line_prefix_before_colon": exception_first_line_prefix,
            "exception_lines": exception_lines,
            "span_indices": [s, e],
        }
        segments_info.append(obj)
        jout.write(json.dumps(obj, ensure_ascii=False) + "\n")

        # 纯文本输出
        segment_indices = before_idx + list(range(s, e + 1)) + after_idx
        segments_indices.append(segment_indices)

        if add_divider:
            out.write(f"----- SEGMENT {seg_no} START -----\n")
            for idx in segment_indices:
                out.write(all_lines[idx])
            out.write(f"----- SEGMENT {seg_no} END -----\n")
        else:
            for idx in segment_indices:
                out.write(all_lines[idx])

print(
    f"提取完成，共生成 {len(segments_info)} 个异常片段；上下文各保留 {ctx_before}/{ctx_after} 条。\n"
    f"文本文件：{output_file}\nJSONL 文件：{jsonl_file}"
)


# print(json.dumps(segments_info[:1], ensure_ascii=False, indent=2))  # 调试：看看第一个对象
