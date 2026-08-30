"""Frozen, reviewer-ready regression contract for the fixture demo."""

DEMO_EVALUATION_CASES = [
    {"subject_id": "CAR3666470", "expected_step": 2, "expected_ids": ["CAR4145453", "CAR4103273", "CAR4201460"], "scenario": "10-mile radius expansion"},
    {"subject_id": "NWM1511509", "expected_step": 2, "expected_ids": ["NWM1464074", "NWM1535239", "NWM1455663"], "scenario": "10-mile radius expansion"},
    {"subject_id": "NWM1537146", "expected_step": 3, "expected_ids": ["NWM1481550", "NWM1500701", "NWM1455663"], "scenario": "six-month approval"},
    {"subject_id": "CAR4214421", "expected_step": 3, "expected_ids": ["CAR4211189", "CAR4183660", "CAR4109691", "CAR4104599", "CAR4105787"], "scenario": "six-month approval"},
    {"subject_id": "CAR4177645", "expected_step": 4, "expected_ids": ["CAR4115854", "CAR4201460", "CAR4115843"], "scenario": "six-month radius expansion"},
    {"subject_id": "NWM1509670", "expected_step": 4, "expected_ids": ["NWM1472994", "NWM1512480", "NWM1491379"], "scenario": "six-month radius expansion"},
    {"subject_id": "REC2841167", "expected_step": 5, "expected_ids": ["REC2909173", "REC9363047", "REC4847306", "REC3001377"], "scenario": "twelve-month approval"},
    {"subject_id": "REC7496324", "expected_step": None, "expected_ids": [], "scenario": "insufficient evidence"},
    {"subject_id": "NWM1354147", "expected_step": None, "expected_ids": [], "scenario": "insufficient evidence"},
    {"subject_id": "CAR3638662", "expected_step": 2, "expected_ids": ["CAR4104412", "CAR4104607", "CAR3557812"], "scenario": "manual rejection review"},
]
