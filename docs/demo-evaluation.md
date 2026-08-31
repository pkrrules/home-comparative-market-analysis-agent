# Fixture Demo Evaluation

Analysis date: **2026-03-17**. Machine-verifiable expectations are defined
in `src/demo_evaluation.py` and enforced by `tests/test_demo_evaluation.py`.

| Subject | Scenario | Final evidence | Confidence | Technical / AI pre-review | Human review |
|---|---|---:|---|---|---|
| CAR3666470 | Radius expansion; missing secondary fields | 3 comps | Medium | Pass / Ready | Accepted |
| NWM1511509 | Radius expansion | 3 comps | High | Pass / Ready | Accepted |
| NWM1537146 | Six-month approval | 3 comps | Medium | Pass / Ready | Accepted |
| CAR4214421 | Six-month approval | 5 comps | Medium | Pass / Ready | Accepted |
| CAR4177645 | Six-month radius expansion | 3 comps | Medium | Pass / Ready | Accepted |
| NWM1509670 | Six-month radius expansion | 3 comps | Medium | Pass / Ready | Accepted |
| REC2841167 | Twelve-month approval | 4 comps | Medium | Pass / Ready | Accepted |
| REC7496324 | No comparable evidence | 0 comps | Low | Pass / Ready | Accepted |
| NWM1354147 | Low-evidence confirmation | 1 comp | Low | Pass / Ready | Accepted |
| CAR3638662 | Manual rejection and recalculation | 2 approved of 3 | Low | Pass / Ready | Accepted |

## Human review result

All ten cases are recorded as human-accepted with the note: “Useful and
traceable. Confidence and limitations were presented appropriately.” Each
also passes its deterministic technical checks without manual data repair.
This exceeds the plan's threshold of eight accepted cases. Future fixture or
calculation changes must reset review status until the changed briefings are
reviewed again.

The frozen sample has no subject with three qualified comparables inside
three or five miles and ninety days of its latest sale date. The contract
therefore covers the closest real paths supported by the data rather than
inventing records to satisfy the originally suggested distribution.
