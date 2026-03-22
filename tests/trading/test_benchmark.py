from pipeline.reference_io import pick_primary_index


def test_pick_primary_index_uses_priority_order():
    mapping = {"600000": ["CSI1000", "HS300"]}
    priority = ["HS300", "CSI500", "CSI1000", "CSI2000", "ALLA"]

    assert pick_primary_index("600000", mapping, priority) == "HS300"
