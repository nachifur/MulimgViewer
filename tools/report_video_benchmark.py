"""Summarize measured delivery data; never infer a speedup from CPU usage."""
import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    destination = args.results
    rows = json.loads((destination / 'results.json').read_text(encoding='utf-8'))
    summary = json.loads((destination / 'summary.json').read_text(encoding='utf-8'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    assert len(rows) == 8 and all(row['completed'] and row['continuous'] for row in rows)
    assert len({json.dumps(row['source_hashes'], sort_keys=True) for row in rows}) == 1
    assert all(row['decode_dimensions_known'] == 24 for row in rows)
    assert len({row['fast_seek_streams'] for row in rows}) == 1
    assert all(row['output_size'] == [1930, 726] for row in rows)
    assert all(30 <= row['elapsed_seconds'] < 32 for row in rows)
    assert all(row['frame_range'][1] < min(video['frames'] for video in manifest['videos']) for row in rows)
    fields = ['policy','mode','repeat','fps','cpu_percent','rss_avg_mib','rss_peak_mib',
              'p95_gap_ms','max_gap_ms','gui_max_gap_ms','measured_frames','elapsed_seconds',
              'extract_run_p90_seconds','stitch_average_seconds','fast_seek_streams','decode_dimensions_known']
    with (destination / 'runs.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# 24 路真实视频播放实测', '',
        '**结论：本次对照未证明最新双阈值线程调度带来了稳定的 FPS 提升，24 路播放仍有明显卡顿。**', '',
        '## 固定条件', '',
        f'- 视频目录：`{Path(manifest["videos"][0]["path"]).parent}`；24 个真实输入文件。',
        '- 12 个 1080×1080、约 10.1 秒，12 个 1280×720、约 32.233 秒；这不是长视频测试。',
        f'- 本机 {manifest["logical_cpus"]} 逻辑 CPU，物理内存 {manifest["ram_bytes"]/1024**3:.1f} GiB。',
        '- 布局 4×6；单格预览 320×180，实际输出 1930×726；关闭标题、放大镜和自动布局。',
        '- cache_frames=2，cache_multiplier=3；Skip=0；人工 Interval 下限 0.001 秒，保留生产代码的自动间隔控制。',
        '- Performance 处理预算 16；Maximum 处理预算 22。各轮使用同一个可用内存参考值。',
        '- 每轮新进程、独立空磁盘缓存；从第 30 帧开始，预热 20 次实际送帧，再测量 30 秒。',
        '- 新旧策略各两轮、两种性能模式，交错执行顺序。视频源文件的操作系统缓存未强制清空。',
        '- 对照组是同一份当前代码关闭新增“原始帧余量 / 双阈值供给控制”，不是整个历史软件版本。',
        '- 正式初始化逐个调用生产 `_get_meta()`：24 路尺寸已知，其中 12 路获得快速定位资格；两组一致。',
        '- 窗口隐藏，但使用真实 wx 主事件循环并完成 display_bitmap/SetBitmap；测的是 GUI 送帧，不是物理屏幕刷新率。', '',
        '## 两轮中位数', '',
        '| 模式 | 对照 FPS | 新策略 FPS | 变化 | 对照 P95 间隔 | 新策略 P95 间隔 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in summary:
        old, new = row['previous-policy'], row['current']
        name = 'Performance' if row['mode'] == 3 else 'Maximum'
        lines.append(f'| {name} | {old["fps"]:.3f} | {new["fps"]:.3f} | {row["fps_gain_percent"]:+.1f}% | '
                     f'{old["p95_gap_ms"]/1000:.2f} s | {new["p95_gap_ms"]/1000:.2f} s |')
    lines += ['', '这里的 P95 是每轮已完成送帧间隔的 95% 分位数，再取两轮中位数；'
              'FPS 分母包含测量窗口末尾尚未送出下一帧的等待。', '',
              '| 模式 / 策略 | FPS 两轮范围 | 平均 CPU | 平均 RSS | 峰值 RSS中位数 |',
              '| --- | ---: | ---: | ---: | ---: |']
    for row in summary:
        for policy in ('previous-policy', 'current'):
            values = [r['fps'] for r in rows if r['mode'] == row['mode'] and r['policy'] == policy]
            data = row[policy]
            label = ('Performance' if row['mode'] == 3 else 'Maximum') + (' / 对照' if policy == 'previous-policy' else ' / 新策略')
            lines.append(f'| {label} | {min(values):.3f}–{max(values):.3f} | {data["cpu_percent"]:.1f}% | '
                         f'{data["rss_avg_mib"]:.0f} MiB | {data["rss_peak_mib"]:.0f} MiB |')
    lines += ['', 'CPU 是应用和 FFmpeg 子进程合计、按整机全部逻辑核为 100%；RSS 是进程工作集相加，'
              '共享页可能重复计入。测试未固定其他进程负载或 CPU 频率，且每组只有两轮，不能将小幅变化视作稳定收益。', '',
              '## 额外参数实验：Maximum，缓存倍数 10', '']
    extra_path = destination / 'cache10_current4' / 'result.json'
    if extra_path.exists():
        extra = json.loads(extra_path.read_text(encoding='utf-8'))
        base = next(row['current'] for row in summary if row['mode'] == 4)
        lines += [f'只做一轮，其余条件相同。FPS 为 **{extra["fps"]:.3f}**，相对当前倍数 3 的两轮中位数约 '
                  f'{(extra["fps"]/base["fps"]-1)*100:+.1f}%；但 P95 间隔变为 **{extra["p95_gap_ms"]/1000:.2f} 秒**，'
                  f'最大已完成间隔 **{extra["max_gap_ms"]/1000:.2f} 秒**。', '',
                  f'CPU {extra["cpu_percent"]:.1f}%，平均 RSS {extra["rss_avg_mib"]:.0f} MiB，峰值 {extra["rss_peak_mib"]:.0f} MiB。'
                  '这说明更大批次可提高平均吞吐，但并未改善这次实测的尾部卡顿；不能把它作为无条件推荐。', '']
    lines += ['## 观察与后续定位方向', '',
        '- 8 轮测量的帧 ID 均连续，且所有 24 路视频仍未到结尾，结果不包含部分视频结束后负载下降。',
        '- 新策略的平均 FPS 改善不稳定；Performance 的中位数反而下降。不能依据功能回归测试通过宣称实际提速。',
        '- 正式测试中 GUI 50ms 心跳最大间隔总体小于 0.25 秒，而送帧存在数秒间隔；主要问题仍在生产/供给链路。',
        '- 拆帧完整批次完成时间和拼接耗时都远高于 1ms。需重点分析补货触发时机、整段拆帧 Future 阻塞后续拼接、'
        '频繁启动 FFmpeg，以及线程切换是否适得其反；这些是定位方向，不是本测试已证明的单一根因。',
        '- 不应只优化平均 FPS 或 CPU 占用，还应同时约束 P95 / 最大送帧间隔。', '',
        '## 原始数据与复现', '',
        '- [逐轮 CSV](runs.csv)、[汇总 JSON](summary.json)、[全部采样与送帧时间](results.json)。',
        '- 每个运行子目录保存完整 result.json 与日志；记录源码 SHA-256，8 轮的源码一致。',
        '- 预跑曾遗漏元数据初始化；`../video_playback/` 内的预跑数字全部排除，仅保留其有效输入清单。',
        '- 测试脚本：`tools/benchmark_video_playback.py`，报告脚本：`tools/report_video_benchmark.py`。', '',
        '```powershell', 'python tools/benchmark_video_playback.py --folder "D:\\ncfey\\Desktop\\test_img\\test_video" --output benchmarks/new_run/manifest.json',
        'python tools/benchmark_video_playback.py --manifest benchmarks/new_run/manifest.json --output benchmarks/new_run/results --matrix --duration 30 --timeout 110', '```', '']
    (destination / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(str(destination / 'report.md'))


if __name__ == '__main__':
    main()
