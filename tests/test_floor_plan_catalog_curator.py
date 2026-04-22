from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed


def test_floor_plan_catalog_seed_exposes_minimum_curated_shape():
    seed = FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox={"width": 468.0, "height": 792.0},
        rooms=[],
        source_layers=[],
        block_refs=[],
        readiness={
            "status": "ready_for_catalog",
            "issues": [],
        },
    )

    payload = seed.model_dump()

    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["canonical_unit"] == "inch"
    assert payload["readiness"]["status"] == "ready_for_catalog"
