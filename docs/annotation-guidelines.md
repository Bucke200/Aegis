# Annotation Guidelines

Version: draft for the blind 180-item pilot (`guideline_version = v1-pilot`).
These rules are ratified or amended at the end of the pilot; every amendment
bumps the version and triggers relabelling of affected pilot items.

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
  ordinary hard cases.
- **Cap sessions at ~200 items.** Aim for roughly 20 seconds per item.
- **Do not fix the text.** Label the text as written. If a template is
  unnatural or broken, still label it if the intent is clear; note systemic
  template problems in the pilot report instead.
- The `import` command rejects any label outside the six classes plus
  `ambiguous` (and `discard` for reviewers).

## 4. Hard boundaries (draft; ratified in the pilot)

These four boundaries decide the pilot. The pilot produces one written rule
per boundary in this section, replacing these drafts.

1. **Criticism vs harassment.** Attack the argument, not the person. Policy
   disagreement, performance criticism, and negative opinion are `criticism`.
   Insults, slurs, humiliation, or sustained personal hostility are
   `harassment`, even when wrapped in a political point.
2. **Harassment vs violent_threat.** Harassment wants the person to feel bad or
   go away; a violent threat wants them harmed. Wishes ("someone should kill
   X"), conditional threats ("if X comes here..."), and stated intent are
   `violent_threat`. Abuse without any harm statement is `harassment`.
3. **Incitement vs violent_threat.** A threat is the author acting; incitement
   is the author recruiting others ("everyone should...", "let's..."). A
   first-person threat that also calls others to act is labelled by the
   author's own commitment: `violent_threat`.
4. **Quoted or reported threats.** Reporting someone else's threat is not the
   author's threat. Quotes, screenshots, news reporting, and "look what he
   said" are `none` unless the author endorses, amplifies, or urges the act --
   then label by the endorsement (`incitement` or `violent_threat`).

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
  overall with Cohen's kappa. Target kappa >= 0.7 on the pilot. If the target
  is missed, revise this document, regenerate candidates if needed, and redo
  the pilot; relabel only after the guidelines are stable.
- **Second-person availability:** if no Hindi-fluent reviewer is available,
  relabel the 25% sample yourself after at least a week's gap and record it in
  the pilot report as a known weakness.

## 8. Workflow

```bash
python -m aegis.eval generate --per-class 10 --seed 7 --out data/labelling/candidates.jsonl
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

- **Pilot:** 10 candidates per class per language (180 items). Exit criteria:
  measured seconds per item, kappa >= 0.7, and one written rule per hard
  boundary in section 4.
- **Gate set target:** 100 per class per language (1,800 items), expandable to
  the design target of 300+ later.
- **Estimate:** ~20 s/item => ~10 h for the annotator, 3-4 h for the reviewer.

## 10. Provenance

Every merged item records `intended_label`, `blind_label`, `final_label`,
`annotator`, `reviewer`, `reviewed_at`, `edge_case`, `generator_model`, and
`guideline_version`. Provenance is what lets the reality set replace synthetic
items later and keeps the calibrator honest.
