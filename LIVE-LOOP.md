# The live loop

Five photos (top and four sides) → photo quality gate → **Muse Spark** finds
and names pieces and supplies centre points → **SAM 3.1** cuts out masks at
those points → Spark checks the masked close-ups → review and confirm →
inventory → **Muse Wonder** proposes placements → BinBuild's validator checks
the design → Spark writes the step words → illustrated booklet.

The phone makes the whole-photo and SAM passes as separate requests. SAM does
not identify pieces or independently discover ones that Spark missed. If SAM
fails, review keeps Spark's whole-photo proposals and says so. The quality gate
checks image usability and performs a probabilistic physical-photo check; it
cannot prove a photo is genuine. See [SAM-3-1.md](SAM-3-1.md) and
[IMAGE-GUARDRAILS.md](IMAGE-GUARDRAILS.md).

Wonder is asked to design from the supported, confirmed pieces; the validator
checks inventory counts and the represented geometry and connections. A
failed check is sent back for another attempt, up to the configured limit.
The background job is polled by the phone. Spark writes words only: BinBuild
keeps the checked pieces, placements, and pictures. If Spark cannot provide
usable step words, the booklet retains BinBuild's original text.

The sample bin contains the **Oct 28** kit photographs and corrections, plus
pre-computed outlines from SAM replies recorded **Oct 28 ET**. Loading it needs
no model call. The recorded Wonder example is from an **Oct 29** run on the
kit's inventory, not the viewer's bin; no model call is needed to see it.

## Recorded measurements

These are individual prior runs, not guarantees for another bin or a new
deployment. The whole-photo fixture records a run on the Oct 28 photo batch
but does not specify the run's date. The SAM run was Oct 28 ET; the fixture
uses a UTC date.

| Recorded work | Result | Source |
|---|---|---|
| Spark whole-photo pass on the Oct 28 batch; run date unspecified | 50 pieces, 44 s | [Inventory loop](INVENTORY-LOOP.md) |
| SAM replies from Oct 28 ET, on that batch | 50 masks for 50 prompted points; four sequential requests took 11.2 s total and cost $0.01 | [SAM spike](SAM-3-1.md), [recorded fixture](tests/fixtures/kit-batch-sam-recorded.json) |
| Spark close-up check in the recorded SAM fixture; run date unspecified | 48 s for four contact sheets | [SAM spike](SAM-3-1.md) |
| Wonder Simple House, Oct 29 | First attempt passed the validator; 88 s and $0.20 | [Wonder designer](WONDER-DESIGNER.md), [recorded fixture](tests/fixtures/wonder-house-recorded.json) |

In the recorded kit run, **11 of 50 labels still needed correction** after
SAM and the Spark close-up check, plus one shape-wording correction. Wonder
can fail to find a valid design, especially with a small bin; the app reports
the failure instead of showing an unchecked build. Generated designs have not
yet been hand-built, so a passing validator is not a physical stability test.
The owner still needs to run the complete new flow live and build a result.
