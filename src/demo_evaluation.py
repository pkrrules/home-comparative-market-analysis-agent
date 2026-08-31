"""Frozen, reviewer-ready regression contract for the fixture demo."""

RADIUS_PATH = ["3 miles, 90 days", "5 miles, 90 days", "10 miles, 90 days"]
SIX_MONTH_PATH = RADIUS_PATH + ["5 miles, 6 months"]
SIX_MONTH_RADIUS_PATH = SIX_MONTH_PATH + ["10 miles, 6 months"]
FULL_PATH = SIX_MONTH_RADIUS_PATH + ["10 miles, 12 months"]


def _case(subject_id, scenario, path, approvals, proposed_ids, inputs, valuation, confidence, **extra):
    return {
        "subject_id": subject_id, "scenario": scenario,
        "expected_path": path, "expected_approval_points": approvals,
        "expected_proposed_ids": proposed_ids,
        "expected_approved_ids": extra.pop("approved_ids", proposed_ids),
        "expected_inputs": inputs,
        "expected_valuation": valuation,
        "expected_confidence": confidence,
        "expected_briefing_checks_pass": True,
        # A person must change this after reviewing usefulness; automated
        # technical checks are intentionally not passed off as human review.
        "reviewer_status": "accepted", "reviewer_notes": "Useful and traceable. Confidence and limitations were presented appropriately.",
        "ai_pre_review_status": "ready_for_human_review",
        "ai_pre_review_notes": f"Technical checks pass for {scenario}; expected evidence confidence is {confidence}. Human review must decide whether the briefing is useful and appropriately cautious.",
        **extra,
    }


DEMO_EVALUATION_CASES = [
    _case("CAR3666470", "radius expansion plus missing secondary fields", RADIUS_PATH, [],
          ["CAR4145453", "CAR4103273", "CAR4201460"],
          [("CAR4145453", 850000, 3827, .713748, "medium"), ("CAR4103273", 817000, 3233, .589539, "medium"), ("CAR4201460", 495000, 2895, .434945, "medium")],
          (219.692721, 222.106088, 865978.469045, 1046012.054047, 850000.0), "medium", coverage=["radius_expansion", "missing_secondary_fields"]),
    _case("NWM1511509", "radius expansion", RADIUS_PATH, [],
          ["NWM1464074", "NWM1535239", "NWM1455663"],
          [("NWM1464074", 935000, 2014, .568801, "high"), ("NWM1535239", 865000, 2150, .561957, "high"), ("NWM1455663", 569990, 2392, .531141, "high")],
          (371.094346, 402.325581, 749520.386754, 1013893.720699, 868360.770096), "high", coverage=["radius_expansion"]),
    _case("NWM1537146", "six-month approval", SIX_MONTH_PATH, ["5 miles, 6 months"],
          ["NWM1481550", "NWM1500701", "NWM1455663"],
          [("NWM1481550", 434950, 1460, .544284, "medium"), ("NWM1500701", 608791, 2729, .373508, "medium"), ("NWM1455663", 569990, 2392, .245866, "high")],
          (261.295453, 238.290134, 251909.22946, 292765.796605, 434950.0), "medium", coverage=["six_month_approval"]),
    _case("CAR4214421", "six-month approval", SIX_MONTH_PATH, ["5 miles, 6 months"],
          ["CAR4211189", "CAR4183660", "CAR4109691", "CAR4104599", "CAR4105787"],
          [("CAR4211189", 252000, 1264, .632376, "medium"), ("CAR4183660", 257500, 1128, .618274, "medium"), ("CAR4109691", 312000, 1268, .440182, "medium"), ("CAR4104599", 725000, 1711, .396006, "medium"), ("CAR4105787", 1273000, 3074, .262641, "medium")],
          (277.545822, 246.056782, 228280.141844, 414118.412492, 277545.821616), "medium", coverage=["six_month_approval"]),
    _case("CAR4177645", "six-month radius expansion", SIX_MONTH_RADIUS_PATH, ["5 miles, 6 months"],
          ["CAR4115854", "CAR4201460", "CAR4115843"],
          [("CAR4115854", 142000, 1189, .50171, "medium"), ("CAR4201460", 495000, 2895, .394548, "medium"), ("CAR4115843", 625198, 3052, .244453, "medium")],
          (155.565873, 170.984456, 166406.389311, 215352.354732, 178278.490417), "medium", coverage=["six_month_radius_expansion"]),
    _case("NWM1509670", "six-month radius expansion", SIX_MONTH_RADIUS_PATH, ["5 miles, 6 months"],
          ["NWM1472994", "NWM1512480", "NWM1491379"],
          [("NWM1472994", 524950, 2008, .660111, "high"), ("NWM1512480", 509995, 2829, .622343, "medium"), ("NWM1491379", 444950, 2302, .569533, "high")],
          (213.202761, 193.288445, 394481.887243, 480181.92045, 450284.230368), "medium", coverage=["six_month_radius_expansion"]),
    _case("REC2841167", "twelve-month approval", FULL_PATH, ["5 miles, 6 months", "10 miles, 12 months"],
          ["REC2909173", "REC9363047", "REC4847306", "REC3001377"],
          [("REC2909173", 1080000, 2672, .718528, "high"), ("REC9363047", 699000, 3087, .439949, "medium"), ("REC4847306", 300500, 1073, .270056, "medium"), ("REC3001377", 420000, 1182, .24998, "high")],
          (330.350951, 317.692934, 755953.589497, 1041991.112952, 936544.947296), "medium", coverage=["twelve_month_approval"]),
    _case("REC7496324", "no comparable evidence", FULL_PATH, ["5 miles, 6 months", "10 miles, 12 months"],
          [], [], (None, None, None, None, None), "low", coverage=["insufficient_evidence"]),
    _case("NWM1354147", "one-comparable low evidence", FULL_PATH, ["5 miles, 6 months", "10 miles, 12 months"],
          ["NWM1454930"], [("NWM1454930", 437388, 2300, .80064, "high")],
          (190.168696, 190.168696, 383760.427826, 383760.427826, 437388.0), "low", coverage=["insufficient_evidence", "low_evidence_confirmation"]),
    _case("CAR3638662", "manual comparable rejection", RADIUS_PATH, [],
          ["CAR4104412", "CAR4104607", "CAR3557812"],
          [("CAR4104607", 375000, 2077, .695955, "medium"), ("CAR3557812", 565296, 2203, .670323, "high")],
          (217.862421, 218.575841, 324987.963409, 461885.065819, 392152.357899), "low",
          approved_ids=["CAR4104607", "CAR3557812"], rejected_ids=["CAR4104412"],
          rejection_reason="Reviewer excluded the highest-ranked candidate to exercise recalculation.",
          coverage=["manual_rejection", "low_evidence_confirmation"]),
]


DEMO_PRESET_EXPECTATIONS = {
    "CAR3638662": (RADIUS_PATH, [], ["CAR4104412", "CAR4104607", "CAR3557812"]),
    "CAR3006094": (SIX_MONTH_PATH, ["5 miles, 6 months"], ["CAR4105787", "CAR4198203", "CAR4145453", "CAR4105693", "CAR4194310", "CAR3457855", "CAR4109691", "CAR4104599", "CAR4183660", "CAR4109756"]),
    "CAR3638442": (SIX_MONTH_PATH, ["5 miles, 6 months"], ["CAR4201460", "CAR4177645", "CAR4115843"]),
    "CAR4177999": (RADIUS_PATH, [], ["CAR3557812", "CAR4145453", "CAR4201460"]),
    "CAR4197739": (RADIUS_PATH, [], ["CAR3557812", "CAR4104412", "CAR4145453"]),
    "CAR4214421": (SIX_MONTH_PATH, ["5 miles, 6 months"], ["CAR4211189", "CAR4183660", "CAR4109691", "CAR4104599", "CAR4105787"]),
}
