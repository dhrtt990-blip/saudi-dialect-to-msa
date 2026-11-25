"""Build the private submission report from verified saved R1 artifacts.

Use the bundled document Python runtime. Missing model results cause a failure,
not placeholder model scores. Human judgments may remain explicitly pending.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT


def read(path):
    return json.loads(Path(path).read_text())


def build(root: Path, out: Path) -> None:
    release = read(root / 'release_manifest.json')
    metrics = read(root / 'results/v3_r1/metrics.json')
    summary = read(root / 'results/v3_r1/aggregate_summary.json')
    prep = read(root / 'data/processed_v3_r1/prep_report.json')
    run = root / release['training_run_directory']
    provenance = read(run / 'provenance.json')
    export = read(run / 'export_manifest.json')
    safety = read(root / 'results/v3_r1/safety_check.json')
    demo = read(root / 'evidence/v3_r1/local_demo.json')
    assert provenance['status'] == 'training_saved' and export['successful_reload']
    assert metrics['meta']['n'] == 100 and not metrics['meta']['dry_run'] and not metrics['meta']['partial']
    assert all(x['n'] == 100 for x in summary['systems'].values())
    assert release['golden_sha256'] == prep['golden_sha256'] == summary['golden_sha256']

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.78)
    section.left_margin = section.right_margin = Inches(.85)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Arial', Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.12
    for name in ('Title', 'Subtitle', 'Heading 1', 'Heading 2'):
        doc.styles[name].font.name = 'Arial'
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles['Title'].font.size = Pt(25)
    doc.styles['Heading 1'].font.size = Pt(16)
    doc.styles['Heading 2'].font.size = Pt(12)

    def para(text, style=None):
        return doc.add_paragraph(text, style)

    def heading(text):
        doc.add_heading(text, 1)

    def table(headers, rows):
        t = doc.add_table(rows=1, cols=len(headers))
        t.autofit = True
        for cell, label in zip(t.rows[0].cells, headers):
            cell.text = str(label)
            shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), '18384E'); cell._tc.get_or_add_tcPr().append(shade)
            for r in cell.paragraphs[0].runs:
                r.bold = True; r.font.color.rgb = RGBColor(255, 255, 255)
        repeat = OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
        for i, values in enumerate(rows):
            cells = t.add_row().cells
            for cell, value in zip(cells, values):
                cell.text = str(value)
                if i % 2 == 0:
                    shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), 'F1F5F8'); cell._tc.get_or_add_tcPr().append(shade)
        for row in t.rows:
            for cell in row.cells:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                borders = OxmlElement('w:tcBorders')
                for side in ('top', 'left', 'bottom', 'right'):
                    edge = OxmlElement('w:' + side)
                    for k, v in [('val', 'single'), ('sz', '5'), ('color', 'D9D9D9')]: edge.set(qn('w:' + k), v)
                    borders.append(edge)
                cell._tc.get_or_add_tcPr().append(borders)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(5)
                    p.paragraph_format.space_before = Pt(5)
                    for r in p.runs: r.font.size = Pt(10)
        para('')
        return t

    def arabic(text):
        p = para(text)
        bidi = OxmlElement('w:bidi'); p._p.get_or_add_pPr().append(bidi)
        for r in p.runs:
            rtl = OxmlElement('w:rtl'); r._r.get_or_add_rPr().append(rtl)
        return p

    para('Saudi Dialect to MSA Travel Desk Evaluation', 'Title')
    para('Golden V3 R1', 'Subtitle')
    s = summary['systems']
    para(f"We evaluated a prompted untuned Qwen3 model, a LoRA-tuned model, and the tuned model with fact verification on the same 100 frozen messages. They passed the automatic checks on {s['baseline']['auto_pass']}/100, {s['tuned']['auto_pass']}/100 and {s['full']['auto_pass']}/100 messages respectively. These counts do not establish semantic correctness. Human meaning and key-fact judgments remain pending wherever the saved evaluation marks them unjudged.")
    para('KAUST Academy NLP Applications | Darb Aljawza Travel booking support')
    para('Team: Abdulrahman Alharthi, Yasser Al-Hajlah, Musaad Al-Qahtani and Mohammed Al-Rashidi.')
    para(f"Release code commit: {release['code_commit']}")

    heading('Task and workflow')
    para('The system rewrites short Saudi-dialect customer messages into formal Modern Standard Arabic for a fictional travel agency. It preserves the customer’s request and factual details; it does not answer the request, invent a booking detail, or make a promise on behalf of the agency. When a date, destination or booking reference is required and absent, it presents a question for the employee to ask the customer.')
    para('For a rewrite, the pipeline compares supported numbers, dates, times, Latin text, listed places and days, and explicitly supplied names. It requests one repair after a detected mismatch and withholds the rewrite if the mismatch persists. This bounded checker cannot determine full semantic equivalence.')

    heading('Frozen benchmark and data separation')
    para('Golden V3-R1 contains 100 messages, 335 labelled key facts and 40 messages lacking a required detail. The exact file remained unchanged throughout this run. Earlier V2.2 results and weights are retained as historical evidence and were not substituted for the new tuned result.')
    para(f"Golden SHA-256: {release['golden_sha256']}")
    para('Frozen data commit: 51127bdfb65a19adb763501d139515dd4479ff27. Activation commit: 1fe1f8a0e10813cb421608831938221135cba735. Training source checkout: ' + provenance['code_commit'] + '.')
    table(['Preparation stage', 'Count'], [
        ['Raw Saudi and MSA corpus rows', prep['loaded']['corpus_rows_in_file']],
        ['Cleaned corpus rows selected', prep['loaded']['corpus']],
        ['Synthetic pairs generated', prep['loaded']['synthetic']],
        ['Removed during assembly cleaning', sum(prep['dropped_in_cleaning'].values())],
        ['Removed for Golden text overlap', prep['removed_for_golden_overlap']],
        ['Removed for Golden distinctive facts', prep['removed_for_shared_fact']],
        ['Written training and validation pairs', f"{prep['train']} / {prep['val']}"],
        ['Remaining Golden overlap', prep['overlap_remaining_after_filter']],
    ])
    para('Both splits were checked against Golden sources and references for normalized exact matches, containment, near duplicates and distinctive facts. Thresholds were 0.8 for near duplicates and 0.6 for shared content. A separate reread of the written files found zero remaining text and distinctive-fact matches. Mac and Colab produced byte-identical splits. These checks do not prove semantic independence; synthetic templates and the benchmark share an AI-assisted drafting process.')

    heading('Training and saved model')
    config = read(run / 'training_config.json')
    train_metrics = read(run / 'train_metrics.json')
    table(['Setting', 'Recorded value'], [
        ['Base model', export['base_model']], ['Base model revision', export['base_revision']],
        ['GPU', provenance['gpu']], ['Seed', provenance['seed']],
        ['LoRA rank and alpha', '16 / 32'], ['LoRA dropout and targets', '0.05 / all linear layers'],
        ['Epochs and learning rate', f"{config['num_train_epochs']} / {config['learning_rate']}"],
        ['Maximum tokens and effective batch', '768 / 16'],
        ['Optimizer steps completed', provenance['global_step']],
        ['Trainer runtime seconds', round(train_metrics['train_runtime'], 1)],
        ['Training and final save elapsed seconds', round(provenance['elapsed_seconds'], 1)],
        ['Peak allocated GPU GiB', round(provenance['peak_gpu_bytes'] / 1024**3, 2)],
    ])
    para('Loss was restricted to assistant tokens. The run saved checkpoints, configuration, library versions, loss history and the final adapter in a distinct directory. An initial attempt stopped before training because Colab’s optional torchao 0.10.0 conflicted with PEFT. Removing that unused optional package allowed float16 LoRA training to proceed. The failed attempt remains in the evidence bundle.')
    para('Recorded software: Python ' + provenance['python'] + '; ' + '; '.join(f"{name} {provenance['versions'][name]}" for name in ('torch', 'transformers', 'peft', 'trl')) + '. Loaded-module and installed-package versions are recorded separately in the provenance file after the environment repair.')
    para('The saved adapter was reloaded into the pinned base model and generated five nonempty validation rewrites. This verifies restoration and inference, not benchmark quality. The untuned and merged models were exported with the same converter revision and Q8_0 setting for the comparison.')
    para('Adapter SHA-256: ' + export['adapter_sha256'])
    history = read(run / 'train_log_history.json')
    training_points = [(x['step'], x['loss']) for x in history if 'step' in x and 'loss' in x]
    validation_points = [(x['step'], x['eval_loss']) for x in history if 'step' in x and 'eval_loss' in x]
    if training_points:
        os.environ.setdefault('MPLCONFIGDIR', str(out.parent / '.mpl-cache'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 2.6), layout='constrained')
        ax.plot(*zip(*training_points), label='Training loss', color='#18384E')
        if validation_points:
            ax.plot(*zip(*validation_points), 'o-', label='Validation loss', color='#A65B26')
        ax.set(xlabel='Optimizer step', ylabel='Cross entropy loss')
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(frameon=False)
        chart = out.parent / 'training_loss.png'
        chart.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(chart, dpi=180)
        plt.close(fig)
        doc.add_picture(str(chart), width=Inches(6.6))
        para('Training and validation loss describe the training-source split. They do not measure Golden semantic correctness.')

    heading('Comparison on the same 100 messages')
    table(['System', 'Released', 'Auto pass', 'Repaired', 'Withheld'], [
        [label, f"{s[key]['released']}/100", f"{s[key]['auto_pass']}/100", s[key]['repaired'], f"{s[key]['withheld']}/100"]
        for key, label in [('baseline', 'Prompted baseline'), ('tuned', 'LoRA alone'), ('full', 'Full pipeline')]
    ])
    para('The three systems rewrite every message under the documented comparison protocol, so the missing-information check is disabled for this comparison and evaluated separately. The baseline prompt was fixed before this R1 evaluation. Temperature is zero and thinking is disabled. Automatic passes require supported facts, no strong lexicon dialect flag, and no unchanged copy where rewriting is required. Human correctness is a separate outcome.')
    table(['Automatic message error', 'Baseline', 'LoRA', 'Full'], [
        [label, *[s[k]['error_counts'].get(field, 0) for k in ('baseline', 'tuned', 'full')]]
        for field, label in [('dropped_fact', 'Missing supported fact'), ('changed_fact', 'Changed supported fact'),
                             ('added_fact', 'Added supported fact'), ('name_lost', 'Required name missing'),
                             ('dialect_left', 'Dialect lexicon flag'), ('copied_input', 'Unchanged copy')]
    ])
    para('These are message counts with denominator 100; categories can overlap. They cover the automatic checker’s vocabulary and patterns. Lost or changed labelled facts, added semantic content, and incorrect withholding require the blinded judgments; an unjudged count is not zero.')
    for t in summary['transitions']:
        para(f"{t['before']} to {t['after']}: {t['wrong_to_right']} automatic failures became passes and {t['right_to_wrong']} passes became failures. The saved report lists every ID and distinguishes automatic transitions from human correctness.")

    heading('Missing information and fixed targets')
    needs = metrics['meta']['needs']
    para(f"The unchanged rules asked on {needs['asked_on_incomplete']}/{needs['incomplete']} incomplete messages and requested exactly the labelled details on {needs['asked_exactly']}/{needs['incomplete']}. They asked needlessly on {needs['needless_asks']}/{needs['complete']} complete messages. T4 meets its historical thresholds at 80% exact requests and a needless-ask rate below 10%; seven incomplete messages are still missed.")
    table(['Target', 'Fixed criterion', 'Current outcome'], [
        ['T1', 'At least 10 net human-correct gains and exact two-sided sign test p < 0.05', summary['targets']['T1']['status']],
        ['T2', 'At most 3 released semantic or key-fact problems', summary['targets']['T2']['status']],
        ['T3', 'At most 15 withheld and at most 5 fine outputs withheld', summary['targets']['T3']['status']],
        ['T4', 'At least 80% exact requests and at most 10% needless requests', summary['targets']['T4']['status']],
    ])
    para('T1–T4 were recovered unchanged from the earlier project package. The recovery does not create a new preregistration, and T4 had already been scored when the table was recovered. No threshold was adjusted to fit this R1 outcome.')

    heading('Human review and safety')
    agreement = summary.get('agreement')
    if agreement and agreement['judged_by_both']:
        para(f"Before reconciliation, the raters agreed on {agreement['agree']}/{agreement['judged_by_both']} verdicts. The gate is at least 80% agreement. Original judgments and reconciled values are retained separately.")
    else:
        para('No two-rater human agreement is established for these outputs. Separate blind sheets A and B are included. Identical rewrites are judged once, systems are hidden, and withheld candidates are included to measure unnecessary withholding. The import tool refuses altered texts, mismatched keys and historical sheets; blank cells remain unjudged. The fixed agreement gate is 80% before reconciliation.')
    from collections import Counter
    counts = Counter(x['verdict'] for x in safety['outcomes'])
    para(f"The travel safety suite contains {len(safety['outcomes'])} actual cases. Recorded automatic outcomes: " + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())) + '. RELEASED_CHECKED means the supported-fact and forbidden-text checks passed; it does not establish semantic safety. Human review remains necessary for number words, price-to-booking associations and other meaning-dependent cases.')

    heading('Error analysis')
    analysis_path = root / 'results/v3_r1/error_analysis.json'
    if analysis_path.exists():
        for item in read(analysis_path).get('examples', [])[:3]:
            para(item['heading'], 'Heading 2')
            arabic(item['source'])
            arabic(item['output'])
            para(item['analysis'])
        para('These examples are an assistant’s documented analysis of the actual outputs. They are not two independent human ratings and were not entered as such in the judgment sheets.')
    else:
        para('The saved evaluation report contains per-example errors and transitions. Semantic error judgments remain pending the independent review.')

    heading('Local demonstration and limits')
    para(f"The browser demonstration ran on {demo['device']} with {demo['os']} and Ollama {demo['ollama_version']}. Windows was not tested in this execution.")
    for case in demo['cases']:
        para(case['label'] + ': ' + case['status'] + '. ' + case['observed_result'])
    para('The rule checker misses some complaints and follow-ups and can confuse a listed place or day with another meaning of the same word. Numbers expressed as words and relationships between otherwise preserved facts need semantic review. Corpus sentences are shorter and more general than many booking requests. The evaluation has only 100 AI-assisted, team-reviewed messages and does not establish performance on real customer traffic.')
    para('Corpus licence statements remain inconsistent. New weights, detailed predictions and rating sheets are retained in the private team bundle; public code and aggregate results do not imply permission to publish derived weights. Historical V2.2 evidence remains separate.')
    heading('Reproduction and evidence')
    para('The bundle includes prediction JSONL files, their run metadata, the frozen benchmark, processing reports, training logs and checkpoints, the adapter, blind sheets, safety outputs and the local demonstration record. Recompute the tables from saved predictions with the included reproduction script; no model call or human judgment is invented in that step.')
    para('Repository: https://github.com/dhrtt990-blip/saudi-dialect-to-msa')
    para('Corpus source: https://doi.org/10.5281/zenodo.17776617')
    para('Base model: https://huggingface.co/Qwen/Qwen3-1.7B')
    para('Every deliverable identifies the same release code commit, benchmark digest and adapter digest. The manifest separately records the training source commit and the exact executed training-cell source for provenance.')
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    build(args.root, args.out)
