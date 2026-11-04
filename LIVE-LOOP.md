# The live loop

Five photos (top and four sides) → photo quality gate → **Muse Spark** finds
and names pieces and supplies centre points → **SAM 3.1** cuts out masks at
those points → Spark checks the masked close-ups → review and confirm →
inventory → **Muse Wonder** proposes three different designs → BinBuild checks
each design → choose a checked preview → Spark writes the step words → booklet.

The phone makes the whole-photo and SAM passes as separate requests. SAM does
not identify pieces or independently discover ones that Spark missed. If SAM
fails, review keeps Spark's whole-photo proposals and says so. The quality gate
checks image usability and performs a probabilistic physical-photo check; it
cannot prove a photo is genuine. See [SAM-3-1.md](SAM-3-1.md) and
[IMAGE-GUARDRAILS.md](IMAGE-GUARDRAILS.md).

Spark now defaults to Muse Spark 1.3 on the Meta Model API, with Baseten's
`meta-models/muse-spark-open-1026` as an automatic backup (`BINBUILD_SPARK=meta+baseten`).
The primary gets at most 60 seconds without retries; transport errors,
unreadable replies or cut-off output use the backup only when at least 45
seconds remain in the call budget. A missing Meta key uses Baseten directly.
Fallback never depends on an answer, including “no”, “uncertain” or a wrong
piece count. Use `BINBUILD_SPARK=baseten` or `meta` for one provider alone.
Reports name the actual answering models, including mixed contact sheets.
Measured Spark numbers in these docs used Baseten's model unless stated otherwise.

Wonder chooses the objects from the supported, confirmed shapes, colours and
quantities. There is no fixed target menu. Each alternative is validated
before its preview appears; rejected or repeated layouts are sent back for
another attempt, up to the configured limit. If fewer than three pass, the app
shows only those that passed. These proposals are not physical build tests.
The cache is tied to the exact inventory and source; changed pieces clear the
choices, and stale selections are refused. Choosing a preview uses that same
checked layout rather than asking for a new design. Both long operations are
polled background jobs. Spark writes words only: BinBuild
keeps the checked pieces, placements, and pictures. If Spark cannot provide
usable step words, the booklet retains BinBuild's original text.

The sample bin contains the **Oct 28** kit photographs and corrections, plus
pre-computed outlines from SAM replies recorded **Oct 28 ET**. Loading it needs
no model call. The recorded Wonder example is from an **Oct 29** run on the
kit's inventory, not the viewer's bin; no model call is needed to see it.

Sample pieces and uploaded pieces are separate build contexts. The sample
journey says "Use these sample pieces" and "Try with my own pieces". Book
designs appear only when every required part fits the selected inventory.
Past generated designs are collapsed under "Saved designs for these pieces"
and are filtered to that same inventory. Wheels and axle connections are not
supported, so vehicle suggestions are rejected; round bricks must not be
renamed as wheels in the step text. Finding fresh ideas is an explicit paid
action; simply loading sample images or reading the build list calls no model.

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
