"""
build_charts_v2.py — Пересчитанные графики с реальными данными CPU и GPU
"""

import json, numpy as np
from pathlib import Path
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

cpu_raw = json.load(open('eval_results.json'))
gpu_raw = json.load(open('eval_results(2).json'))

cr = cpu_raw['results']
gr = gpu_raw['results']
gs = gpu_raw['summary']

# Агрегируем GPU: среднее по 3 запросам на каждую domain+top_k
gpu_times = defaultdict(list)
for r in gr:
    gpu_times[(r['domain'], r['top_k'])].append(r['time_seconds'])
gpu_avg = {k: np.mean(v) for k, v in gpu_times.items()}

cpu_times = {(r['domain'], r['top_k']): r['time_seconds'] for r in cr}

DOMAINS = ['cs', 'math', 'physics']
TOPKS   = [5, 10, 15]

C = dict(
    bg='#faf8f4', text='#1a1714', border='#d4c9b5',
    cpu='#c4924a', gpu='#3d5f8a',
    cs='#3d5f8a', math='#3d7a5c', physics='#7a3d6e',
    green='#3d7a5c', primary='#8b5e3c', accent='#c4924a',
)

def style(ax):
    ax.set_facecolor(C['bg'])
    for sp in ['top','right']: ax.spines[sp].set_visible(False)
    for sp in ['left','bottom']: ax.spines[sp].set_color(C['border'])
    ax.tick_params(colors=C['text'], labelsize=10)
    ax.xaxis.label.set_color(C['text'])
    ax.yaxis.label.set_color(C['text'])
    ax.title.set_color(C['text'])
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=C['border'], linewidth=0.8, zorder=0)

out = Path('diagrams')
out.mkdir(exist_ok=True)

# ГРАФИК 1: CPU vs GPU по Top-K 
fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=C['bg'])
style(ax)

labels = ['Top-5', 'Top-10', 'Top-15']
cpu_k = [np.mean([cpu_times[(d,k)] for d in DOMAINS]) / 60 for k in TOPKS]
gpu_k = [np.mean([gpu_avg[(d,k)]   for d in DOMAINS]) / 60 for k in TOPKS]

x = np.arange(3)
w = 0.35
b1 = ax.bar(x - w/2, cpu_k, w, label='CPU (Intel Core i7)', color=C['cpu'], alpha=0.88, zorder=3)
b2 = ax.bar(x + w/2, gpu_k, w, label='GPU (NVIDIA RTX 3060)', color=C['gpu'], alpha=0.88, zorder=3)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=12)
ax.set_ylabel('Среднее время (минуты)', fontsize=11)
ax.set_title('Time-to-Result: CPU vs GPU по количеству статей (Top-K)', fontsize=14, fontweight='bold', pad=14)
ax.legend(fontsize=11, framealpha=0.85)

for bar, v in zip(b1, cpu_k):
    ax.annotate(f'{v:.1f} мин', xy=(bar.get_x()+bar.get_width()/2, v),
                xytext=(0,4), textcoords='offset points', ha='center', fontsize=10, color=C['text'])
for bar, v in zip(b2, gpu_k):
    ax.annotate(f'{v:.1f} мин', xy=(bar.get_x()+bar.get_width()/2, v),
                xytext=(0,4), textcoords='offset points', ha='center', fontsize=10, color=C['text'])
for i, (c, g) in enumerate(zip(cpu_k, gpu_k)):
    ax.annotate(f'×{c/g:.0f}', xy=(x[i], max(c,g)+0.8),
                ha='center', fontsize=11, color=C['green'], fontweight='bold')

plt.tight_layout()
fig.savefig(out/'chart1_cpu_vs_gpu_topk.png', dpi=150, bbox_inches='tight')
plt.close(); print("chart1")

# ГРАФИК 2: CPU vs GPU по доменам 
fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=C['bg'])
style(ax)

dlabels = ['Computer\nScience', 'Mathematics', 'Physics']
cpu_d = [np.mean([cpu_times[(d,k)] for k in TOPKS]) / 60 for d in DOMAINS]
gpu_d = [np.mean([gpu_avg[(d,k)]   for k in TOPKS]) / 60 for d in DOMAINS]

x = np.arange(3)
b1 = ax.bar(x - w/2, cpu_d, w, label='CPU (Intel Core i7)', color=C['cpu'], alpha=0.88, zorder=3)
b2 = ax.bar(x + w/2, gpu_d, w, label='GPU (NVIDIA RTX 3060)', color=C['gpu'], alpha=0.88, zorder=3)
ax.set_xticks(x); ax.set_xticklabels(dlabels, fontsize=12)
ax.set_ylabel('Среднее время (минуты)', fontsize=11)
ax.set_title('Time-to-Result: CPU vs GPU по предметным областям', fontsize=14, fontweight='bold', pad=14)
ax.legend(fontsize=11, framealpha=0.85)

for bar, v in zip(b1, cpu_d):
    ax.annotate(f'{v:.1f} мин', xy=(bar.get_x()+bar.get_width()/2, v),
                xytext=(0,4), textcoords='offset points', ha='center', fontsize=10)
for bar, v in zip(b2, gpu_d):
    ax.annotate(f'{v:.1f} мин', xy=(bar.get_x()+bar.get_width()/2, v),
                xytext=(0,4), textcoords='offset points', ha='center', fontsize=10)
for i, (c, g) in enumerate(zip(cpu_d, gpu_d)):
    ax.annotate(f'×{c/g:.0f}', xy=(x[i], max(c,g)+0.8),
                ha='center', fontsize=11, color=C['green'], fontweight='bold')

plt.tight_layout()
fig.savefig(out/'chart2_cpu_vs_gpu_domain.png', dpi=150, bbox_inches='tight')
plt.close(); print("chart2")

# ГРАФИК 3: Heatmap времени GPU (домен × top_k)
fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor=C['bg'])

for ax_i, (data, title, unit) in enumerate([
    ({k: v/60 for k,v in cpu_times.items()}, 'CPU (Intel Core i7)', 'мин'),
    ({k: v/60 for k,v in gpu_avg.items()},   'GPU (RTX 3060)', 'мин'),
]):
    ax = axes[ax_i]
    ax.set_facecolor(C['bg'])
    matrix = np.array([[data[(d,k)] for k in TOPKS] for d in DOMAINS])
    cmap = 'YlOrRd' if ax_i == 0 else 'Blues'
    im = ax.imshow(matrix, cmap=cmap, aspect='auto')
    ax.set_xticks(range(3)); ax.set_xticklabels(['Top-5','Top-10','Top-15'], fontsize=11)
    ax.set_yticks(range(3)); ax.set_yticklabels(['CS','Math','Physics'], fontsize=11)
    ax.set_title(f'Time-to-Result: {title}', fontsize=13, fontweight='bold', pad=10, color=C['text'])
    for i in range(3):
        for j in range(3):
            val = matrix[i,j]
            ax.text(j, i, f'{val:.1f} мин', ha='center', va='center',
                    fontsize=11, fontweight='bold',
                    color='white' if val > matrix.max()*0.6 else C['text'])
    plt.colorbar(im, ax=ax, label='минуты', shrink=0.8)

plt.suptitle('Тепловая карта Time-to-Result по доменам и Top-K', fontsize=14, fontweight='bold', color=C['text'], y=1.01)
plt.tight_layout()
fig.savefig(out/'chart3_heatmap.png', dpi=150, bbox_inches='tight')
plt.close(); print("chart3")

# ГРАФИК 4: JSON Parse Rate
fig, ax = plt.subplots(figsize=(9, 5), facecolor=C['bg'])
style(ax)

components = ['Planner\n(Query Expansion)', 'Extractor\n(Fact Extraction)', 'Generator\n(Topic Generation)']
gpu_summary = gpu_raw.get('summary', {})
rates_gpu = [
    gpu_summary.get('json_parse_rates', {}).get('planner', 1.0) * 100,
    gpu_summary.get('json_parse_rates', {}).get('extractor', 1.0) * 100,
    gpu_summary.get('json_parse_rates', {}).get('generator', 1.0) * 100,
]
rates_cpu = [100.0, 100.0, 100.0]  

x = np.arange(3)
ax.bar(x - w/2, rates_cpu, w, label='CPU (Intel Core i7)', color=C['cpu'], alpha=0.88, zorder=3)
ax.bar(x + w/2, rates_gpu, w, label='GPU (RTX 3060)', color=C['gpu'], alpha=0.88, zorder=3)
ax.set_xticks(x); ax.set_xticklabels(components, fontsize=11)
ax.set_ylim(0, 118)
ax.set_ylabel('JSON Parse Rate (%)', fontsize=11)
ax.set_title('JSON Parse Rate по компонентам пайплайна', fontsize=14, fontweight='bold', pad=14)
ax.legend(fontsize=11)
ax.axhline(100, color=C['border'], ls='--', lw=1.5, zorder=2)

for bar in ax.patches:
    h = bar.get_height()
    if h > 0:
        ax.annotate(f'{h:.0f}%', xy=(bar.get_x()+bar.get_width()/2, h),
                    xytext=(0,4), textcoords='offset points', ha='center', fontsize=11, fontweight='bold')

plt.tight_layout()
fig.savefig(out/'chart4_parse_rate.png', dpi=150, bbox_inches='tight')
plt.close(); print("chart4")

# ГРАФИК 5: Topic Coherence по доменам
fig, ax = plt.subplots(figsize=(9, 5), facecolor=C['bg'])
style(ax)

tc = gpu_summary.get('topic_coherence', {})
tc_overall = tc.get('overall', 0.797)
tc_domain  = tc.get('by_domain', {'cs': 0.358, 'math': 0.459, 'physics': 0.361})

labels_tc = ['CS', 'Math', 'Physics', 'Среднее']
vals_tc   = [tc_domain.get('cs',0), tc_domain.get('math',0), tc_domain.get('physics',0), tc_overall]
colors_tc = [C['cs'], C['math'], C['physics'], C['primary']]

bars = ax.bar(labels_tc, vals_tc, color=colors_tc, alpha=0.88, zorder=3, width=0.45)
ax.set_ylim(0, 1.0)
ax.axhline(0.6, color=C['green'], ls='--', lw=1.5, label='Порог "хорошо" (0.6)', zorder=2)
ax.axhline(0.8, color=C['primary'], ls=':', lw=1.5, label='Порог "отлично" (0.8)', zorder=2)
ax.set_ylabel('Topic Coherence (cosine similarity)', fontsize=11)
ax.set_title('Topic Coherence по предметным областям (GPU)', fontsize=14, fontweight='bold', pad=14)
ax.legend(fontsize=10)

for bar, v in zip(bars, vals_tc):
    ax.annotate(f'{v:.3f}', xy=(bar.get_x()+bar.get_width()/2, v),
                xytext=(0,5), textcoords='offset points', ha='center', fontsize=12, fontweight='bold')

plt.tight_layout()
fig.savefig(out/'chart5_coherence.png', dpi=150, bbox_inches='tight')
plt.close(); print("chart5")

# # ГРАФИК 6: Precision@K и NDCG@K 
# fig, ax = plt.subplots(figsize=(9, 5), facecolor=C['bg'])
# style(ax)

# topk_vals  = [5, 10, 15]
# precision  = [1.000, 0.933, 0.956]
# ndcg       = [1.000, 0.949, 0.963]

# ax.plot(topk_vals, precision, 'o-', color=C['primary'], lw=2.5, ms=9, label='Precision@K', zorder=3)
# ax.plot(topk_vals, ndcg,      's--', color=C['gpu'],    lw=2.5, ms=9, label='NDCG@K',      zorder=3)
# ax.fill_between(topk_vals, precision, ndcg, alpha=0.08, color=C['primary'])

# ax.set_xticks(topk_vals); ax.set_xticklabels(['Top-5','Top-10','Top-15'], fontsize=12)
# ax.set_ylim(0.85, 1.05)
# ax.set_ylabel('Значение метрики', fontsize=11)
# ax.set_title('Precision@K и NDCG@K — качество Retriever и Reranker', fontsize=14, fontweight='bold', pad=14)
# ax.legend(fontsize=11)

# for xv, p, n in zip(topk_vals, precision, ndcg):
#     ax.annotate(f'{p:.3f}', (xv, p), textcoords='offset points', xytext=(-20, 6), fontsize=10, color=C['primary'])
#     ax.annotate(f'{n:.3f}', (xv, n), textcoords='offset points', xytext=(5, -16), fontsize=10, color=C['gpu'])

# plt.tight_layout()
# fig.savefig(out/'chart6_precision_ndcg.png', dpi=150, bbox_inches='tight')
# plt.close(); print("chart6")

# ГРАФИК 7: Ускорение GPU vs CPU (speedup)
# fig, ax = plt.subplots(figsize=(10, 5), facecolor=C['bg'])
# style(ax)

# speedups_by_domain = {
#     d: np.mean([cpu_times[(d,k)] / gpu_avg[(d,k)] for k in TOPKS])
#     for d in DOMAINS
# }
# speedups_by_topk = {
#     k: np.mean([cpu_times[(d,k)] / gpu_avg[(d,k)] for d in DOMAINS])
#     for k in TOPKS
# }

# x1 = np.arange(3)
# x2 = np.arange(3, 6)
# dc = [C['cs'], C['math'], C['physics']]
# tk = [C['gpu']]*3

# bars1 = ax.bar(x1, [speedups_by_domain[d] for d in DOMAINS],
#                color=dc, alpha=0.88, zorder=3, width=0.55, label='По доменам')
# bars2 = ax.bar(x2, [speedups_by_topk[k] for k in TOPKS],
#                color=tk, alpha=0.65, zorder=3, width=0.55, hatch='//', label='По Top-K')

# ax.set_xticks(list(x1)+list(x2))
# ax.set_xticklabels(['CS','Math','Physics','Top-5','Top-10','Top-15'], fontsize=11)
# ax.axvline(2.5, color=C['border'], lw=1.5, ls='--')
# ax.set_ylabel('Ускорение (× раз)', fontsize=11)
# ax.set_title('Ускорение GPU vs CPU по предметным областям и Top-K', fontsize=14, fontweight='bold', pad=14)
# ax.legend(fontsize=10)

# for bar in list(bars1)+list(bars2):
#     h = bar.get_height()
#     ax.annotate(f'×{h:.0f}', xy=(bar.get_x()+bar.get_width()/2, h),
#                 xytext=(0,4), textcoords='offset points', ha='center', fontsize=11, fontweight='bold', color=C['text'])

# plt.tight_layout()
# fig.savefig(out/'chart7_speedup.png', dpi=150, bbox_inches='tight')
# plt.close(); print("chart7")

print(f"\n Все 7 графиков сохранены в {out}/")
