# Fixture Demo Evaluation

Analysis date: **2026-03-17**. Machine-verifiable expectations are defined
in `src/demo_evaluation.py` and enforced by `tests/test_demo_evaluation.py`.

| Subject | Scenario | Final evidence | Confidence | Technical / AI pre-review | Human review |
|---|---|---:|---|---|---|
| CAR3666470 | Radius expansion; missing secondary fields | 3 comps | Medium | Pass / Ready | Pending |
| NWM1511509 | Radius expansion | 3 comps | High | Pass / Ready | Pending |
| NWM1537146 | Six-month approval | 3 comps | Medium | Pass / Ready | Pending |
| CAR4214421 | Six-month approval | 5 comps | Medium | Pass / Ready | Pending |
| CAR4177645 | Six-month radius expansion | 3 comps | Medium | Pass / Ready | Pending |
| NWM1509670 | Six-month radius expansion | 3 comps | Medium | Pass / Ready | Pending |
| REC2841167 | Twelve-month approval | 4 comps | Medium | Pass / Ready | Pending |
| REC7496324 | No comparable evidence | 0 comps | Low | Pass / Ready | Pending |
| NWM1354147 | Low-evidence confirmation | 1 comp | Low | Pass / Ready | Pending |
| CAR3638662 | Manual rejection and recalculation | 2 approved of 3 | Low | Pass / Ready | Pending |

## Human review protocol

For each row, a reviewer should run the fixture case, inspect the proposed
comparables, search trace, deterministic valuation, limitations, and final
briefing, then change `reviewer_status` to `accepted` or `rejected` and record
specific notes in `reviewer_notes`. Automated checks establish technical
correctness; they do not establish usefulness. The plan's success criterion
is met only after at least eight cases are technically correct and accepted
by a person without manual data repair.

The frozen sample has no subject with three qualified comparables inside
three or five miles and ninety days of its latest sale date. The contract
therefore covers the closest real paths supported by the data rather than
inventing records to satisfy the originally suggested distribution.
