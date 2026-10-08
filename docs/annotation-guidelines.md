# Annotation Guidelines

Version: `v1`, ratified after the 180-item pilot (`guideline_version = v1`).
Amendments bump the version; the pilot ran under the `v1-pilot` drafts, and the
incitement and precedence clauses changed materially at ratification (see the
pilot report in the private `Aegis-data` repository).

## 1. Purpose and the two sets

Two labelled sets serve different jobs:

- **Gate set** (`data/private/golden/intent/`, in the private `Aegis-data`
  repository): synthetic candidates, blind-labelled
  and reviewed, committed to the repository. Its job is to catch detector
  drift in CI. It is not used to fit the calibrator.
- **Reality set** (not committed): real text from public research datasets and
  analyst labels, used later to fit the isotonic calibrator and report honest
  precision and recall. Real threat text never enters the repository.

## 2. Canonical classes

Every item gets exactly one of these six labels, used verbatim in storage, the
UI, and evaluation:

| Label | Meaning | Typical signal |
|---|---|---|
| `none` | No threat and no criticism; neutral or informational | news reports, quotes, logistics |
| `criticism` | Strong disagreement or negative opinion about policies, performance, or conduct, without abuse | "I disagree with X's policy", "poor leadership" |
| `harassment` | Targeted abuse, insults, humiliation, or sustained hostility toward a person | slurs and insults aimed at the person |
| `violent_threat` | A threat or wish of physical harm to a person | "I will shoot X", "someone should stab X" |
| `incitement` | A call for others to act violently against a person or group | "everyone march on X's house", "teach X a lesson" |
| `doxxing` | Publishing or seeking private information (address, phone, email, ID numbers) | leaks of address or contact details |

`none` and `criticism` are non-threat. `harassment`, `violent_threat`,
`incitement`, and `doxxing` are threat classes. Sentiment is irrelevant:
disliking something is not a threat, and anger alone is not a threat.

## 3. How to label

- **Blind and cold.** The sheet never shows the generator's intended class.
  Do not try to guess it; label what the text means to a platform moderator.
  Rows are shuffled per sheet.
- **One label per row.** If you genuinely cannot decide, choose `ambiguous`.
  Ambiguous items are reviewed by the second person; do not use it to avoid
  ordinary hard cases. If the row is broken, refused, duplicated, or otherwise
  unusable as data (not merely hard), choose `unusable`; unusable rows are
  dropped and excluded from kappa.
- **Cap sessions at ~200 items.** Aim for roughly 20 seconds per item.
- **Do not fix the text.** Label the text as written. If a template is
  unnatural or broken, still label it if the intent is clear; note systemic
  template problems in the pilot report instead.
- The `import` command rejects any label outside the six classes plus
  `ambiguous` and `unusable` (and `discard` for reviewers).

## 4. Hard boundaries (ratified `v1`)

These rules were ratified at the end of the 180-item pilot.

1. **Criticism vs harassment.** Attack the argument, not the person.
   - An insult or demeaning epithet aimed at the person makes it `harassment`,
     even when a policy complaint is attached.
   - Harsh words about the policy or conduct ("stupid plan") stay `criticism`.
   - Insults aimed at someone other than the named person are not `harassment`
     of that person.
2. **Harassment vs violent_threat.** Harassment wants the person to feel bad or
   go away; a violent threat wants them harmed.
   - An impersonal wish ("should be stabbed", "someone should shoot") is
     `violent_threat`.
   - Covers threats against the person's home, office, or convoy, not only
     their body.
   - Abuse without any harm statement is `harassment`.
3. **Incitement vs violent_threat.**
   - An addressed call ("brothers", "everyone", "let's", an imperative) is
     `incitement`; an impersonal wish is `violent_threat`.
   - "Teach a lesson" or "make an example" is `incitement` only with a concrete
     cue: a time, a place, a weapon, or a crowd address. Without one it is
     `ambiguous` and goes to the reviewer.
   - Physical mobilisation against the person (march on the office, block the
     convoy) is `incitement`. Calls for legal or accountability action ("arrest
     him", "answer questions", "step down") are `criticism`.
   - A first-person threat that also recruits others is labelled by the
     author's own commitment: `violent_threat`.
4. **Quoted or reported threats.**
   - `none` requires attribution to someone else ("he said", "police said",
     "was threatened").
   - An unattributed announcement ("a plan to hurt her is set") is
     `violent_threat`.
   - Reporting is `none` unless the author endorses or amplifies the act; then
     label by the endorsement.
5. **Precedence when two labels fit.** Apply in order: `doxxing`,
   `violent_threat`, `incitement`, `harassment`, `criticism`, `none`. Doxxing
   wins whenever private data is present, because the leak is the actionable
   harm; "find her at this address tonight" is `doxxing`.

## 5. Edge cases

| Edge case | Rule |
|---|---|
| satire | Label the literal content, not the humour. Satire that only mocks is `criticism`; satire that repeats a threat credibly is labelled by the threat. |
| sarcasm | Same as satire. "Great job, prices are lower now. Not." is `criticism`. |
| quote | See boundary 4. A bare quote is `none`; quoted abuse aimed at shaming the target is `harassment` by context. |
| news | Reporting on threats, arrests, or attacks is `none` unless the report itself endorses or repeats the threat as its own call to action. |
| sentiment | Sadness, fear, or anger without a target and an action is `none`. |
| doxxing with mixed content | If private data is present, label `doxxing` even when the rest is criticism; the leak is the actionable harm. |

## 6. Doxxing and fake PII

- Synthetic doxxing items use only reserved fake data: `example.test` emails,
  obviously invalid numbers, and placeholder addresses.
- Never paste real personal data into a sheet, a commit, an issue, or a chat.
  If real data appears by accident, stop, flag it to the lead, and discard the
  row without recording the content.
- The repository is public: fake credentials in the leak set must not match
  real provider key formats, or GitHub push protection will (correctly) block
  the push. Review the leak set before the first push.

## 7. Review and adjudication

- **Review scope:** all disagreements between intended and blind labels, all
  `ambiguous` items, and a deterministic random 25% slice of the rest. The
  sample is derived from `sha256(f"{seed}:{id}")` ordering, so it is
  reproducible and verifiable at merge time.
- **Reviewer labels blind too.** The review sheet hides both the intended and
  the first annotator's label.
- **Reviewer decisions:**
  - a class label replaces the first label and is final;
  - `ambiguous` drops the item;
  - `discard` drops the item (broken template, duplicate, unusable text).
- **Agreement:** the first annotator vs the generator is tracked per class and
  overall with Cohen's kappa. Unusable rows are excluded from kappa and counted.
  Target kappa >= 0.7 on the pilot. If the target is missed, revise this
  document, regenerate candidates if needed, and redo the pilot; relabel only
  after the guidelines are stable.
- **Redraft rule:** if more than ~10% of a cell (10 rows) is marked unusable, the
  cell's drafts are treated as bad and the whole cell is redrafted rather than
  filled from whatever is left. `stats` reports `unusable_by_cell` and
  `redraft_cells`.
- **Second-person availability:** if no Hindi-fluent reviewer is available,
  relabel the 25% sample yourself after at least a week's gap and record it in
  the pilot report as a known weakness.

## 8. Workflow

The candidate sheet is sampled from the private draft bank, which mixes
hand-written entries, templated variants, and drafts from the benchmarked
models (every item records its drafter so the benchmark can hold out drafts).

```bash
# one-time (and after a model or prompt change): build the private bank
python -m aegis.eval seed-bank --out data/private/banks/hand-written.jsonl
python -m aegis.eval draft --bank-dir data/private/banks \
    --models llama3.2:3b,qwen2.5:3b,gemma3:4b --per-model 3 --attempts 6
python -m aegis.eval check-bank --bank-dir data/private/banks

# then the pilot
python -m aegis.eval generate --bank-dir data/private/banks --per-class 10 --seed 7 \
    --out data/labelling/candidates.jsonl
python -m aegis.eval sheet --candidates data/labelling/candidates.jsonl --out data/labelling/sheet.csv
# annotate sheet.csv in a spreadsheet (the label column), then:
python -m aegis.eval import --sheet data/labelling/sheet.csv --annotator <you>
python -m aegis.eval stats --out data/labelling/stats.json
python -m aegis.eval sample --fraction 0.25 --seed 7
# reviewer fills review-sheet.csv, then:
python -m aegis.eval import --sheet data/labelling/review-sheet.csv --annotator <reviewer> --role reviewer
python -m aegis.eval merge --reviewed data/labelling/reviewed.jsonl --guideline-version v1
```

Everything under `data/labelling/` is gitignored work in progress. Only the
merged `data/private/golden/intent/*.jsonl` files are committed, and only to the
private `Aegis-data` repository (cloned by `make data`).

## 9. Pilot and target

- **Pilot:** completed on 180 items (10 per class per language) with two
  recorded deviations: the first pass was model-assisted and the sheet ids
  exposed the intended class, and no human seconds-per-item figure exists. The
  human check is the 39-row review pass weighted to model drafts and every
  disagreement; kappa on the stated basis (ambiguous excluded) was 0.9042, and
  the eight flagged cells passed the redraft acceptance test at 0% unusable.
  Details in the private pilot report.
- **Gate set target:** 100 per class per language (1,800 items), expandable to
  the design target of 300+ later, drafted under these `v1` rules.
- **Estimate:** ~20 s/item => ~10 h for an annotator, 3-4 h for the reviewer.

## 10. Provenance

Every merged item records `intended_label`, `blind_label`, `final_label`,
`annotator`, `reviewer`, `reviewed_at`, `edge_case`, `generator_model`, and
`guideline_version`. Provenance is what lets the reality set replace synthetic
items later and keeps the calibrator honest.
