"""Propagation data endpoints — solar conditions and band status."""

import logging

from fastapi import APIRouter, HTTPException, Query

from ..services.propagation import get_service, ALL_BANDS

router = APIRouter(prefix="/propagation", tags=["propagation"])
logger = logging.getLogger("elmer.propagation.routes")


@router.get("")
async def get_conditions():
    """Current propagation conditions summary."""
    svc = get_service()
    conditions = await svc.get_current_conditions()

    solar = conditions.solar
    bands = {name: {"day": bc.day, "night": bc.night}
             for name, bc in conditions.bands.items()}

    return {
        "solar_flux": solar.solar_flux,
        "sunspot_number": solar.sunspot_number,
        "a_index": solar.a_index,
        "k_index": solar.k_index,
        "x_ray_flux": solar.x_ray_flux,
        "proton_flux": solar.proton_flux,
        "geomag_storm": solar.geomag_storm,
        "geomag_field": solar.geomag_field,
        "signal_noise": solar.signal_noise,
        "solar_wind": solar.solar_wind,
        "magnetic_field": solar.magnetic_field,
        "bands": bands,
        "vhf": [{"name": v.name, "location": v.location, "status": v.status}
                for v in conditions.vhf],
        "drap": conditions.drap,
        "updated": conditions.updated,
        "source_status": conditions.source_status,
    }


@router.get("/bands")
async def get_bands():
    """Per-band conditions (day and night)."""
    svc = get_service()
    return await svc.get_band_conditions()


@router.get("/solar")
async def get_solar():
    """Solar indices — SFI, SSN, A/K index, flare status."""
    svc = get_service()
    return await svc.get_solar_data()


@router.get("/forecast")
async def get_forecast():
    """Propagation forecast data."""
    svc = get_service()
    return await svc.get_forecast()


@router.get("/history")
async def get_history(hours: int = Query(default=24, ge=1, le=168)):
    """Historical propagation data points."""
    svc = get_service()
    return await svc.get_history(hours=hours)


@router.get("/band/{band}")
async def get_band_detail(band: str):
    """Detail for a specific band including recent history."""
    if band not in ALL_BANDS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown band '{band}'. Valid bands: {', '.join(ALL_BANDS)}",
        )
    svc = get_service()
    result = await svc.get_band_detail(band)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for band '{band}'")
    return result
