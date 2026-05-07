import json

PLANTS = [
  {
    "id": "kpcl_shivanasamudra",
    "name": "Shivanasamudra / Simsha Solar Plant",
    "type": "solar",
    "latitude": 12.3000,
    "longitude": 77.1700,
    "capacity_kw": 15000,
    "ac_capacity_mw": 15,
    "dc_capacity_mw": 18, 
    "ownership": "100% KPCL (State Government)",
    "district": "Mandya",
    "status": "Active",
    "tilt": 15.0,
    "azimuth": 180.0,
    "hover_info": {
      "description": "KPCL's flagship 15 MW solar plant located near the Shivanasamudra waterfalls. Generates power using fixed-tilt modules.",
      "annual_generation_target_mwh": "~16,000",
      "hardware": "Multi-Crystalline Panels",
      "irradiance_kwh_m2_day": "5.2 - 5.4"
    }
  },
  {
    "id": "kpcl_yalesandra",
    "name": "Yalesandra Solar PV Plant",
    "type": "solar",
    "latitude": 12.8931,
    "longitude": 78.1655,
    "capacity_kw": 3000,
    "ac_capacity_mw": 3,
    "dc_capacity_mw": 3.6,
    "ownership": "100% KPCL (State Government)",
    "district": "Kolar",
    "status": "Active",
    "tilt": 15.0,
    "azimuth": 180.0,
    "hover_info": {
      "description": "India's first megawatt-scale, grid-connected solar power plant, commissioned in 2009 over 10.3 acres.",
      "annual_generation_target_mwh": "~4,500",
      "hardware": "Mono-Crystalline Panels (225Wp & 240Wp)",
      "irradiance_kwh_m2_day": "5.3 - 5.5"
    }
  },
  {
    "id": "kpcl_itnal",
    "name": "Itnal Solar PV Plant",
    "type": "solar",
    "latitude": 16.4348,
    "longitude": 74.6740,
    "capacity_kw": 3000,
    "ac_capacity_mw": 3,
    "dc_capacity_mw": 3.6,
    "ownership": "100% KPCL (State Government)",
    "district": "Belagavi",
    "status": "Active",
    "tilt": 15.0,
    "azimuth": 180.0,
    "hover_info": {
      "description": "State-owned decentralized 3 MW generation facility feeding directly into the northern Karnataka local grid.",
      "annual_generation_target_mwh": "~4,300",
      "hardware": "Mono-Crystalline Panels",
      "irradiance_kwh_m2_day": "5.1 - 5.3"
    }
  },
  {
    "id": "kpcl_yapaldinni",
    "name": "Yapaldinni Solar PV Plant",
    "type": "solar",
    "latitude": 16.2475,
    "longitude": 77.4431,
    "capacity_kw": 3000,
    "ac_capacity_mw": 3,
    "dc_capacity_mw": 3.6,
    "ownership": "100% KPCL (State Government)",
    "district": "Raichur",
    "status": "Active",
    "tilt": 15.0,
    "azimuth": 180.0,
    "hover_info": {
      "description": "3 MW grid-connected power plant located in the high-heat, high-irradiance district of Raichur.",
      "annual_generation_target_mwh": "~4,600",
      "hardware": "Mono-Crystalline Panels",
      "irradiance_kwh_m2_day": "5.6 - 5.8"
    }
  },
  {
    "id": "kspdcl_pavagada",
    "name": "Pavagada Solar Park (Shakti Sthala)",
    "type": "solar",
    "latitude": 14.2500,
    "longitude": 77.4500,
    "capacity_kw": 2050000,
    "ac_capacity_mw": 2050,
    "dc_capacity_mw": 2460,
    "ownership": "Managed by KSPDCL (Joint Govt Venture)",
    "district": "Tumkur",
    "status": "Active",
    "tilt": 15.0,
    "azimuth": 180.0,
    "hover_info": {
      "description": "One of the world's largest solar parks spanning 13,000 acres. The state government built and manages the pooling substations and grid infrastructure.",
      "annual_generation_target_mwh": "~4,500,000",
      "hardware": "Mixed (Thin-film & Multi-Crystalline, 15-degree tilt)",
      "irradiance_kwh_m2_day": "5.5 - 6.0"
    }
  },
  {
    "id": "wind_tuppadahalli",
    "name": "Tuppadahalli Wind Farm",
    "type": "wind",
    "latitude": 14.200,
    "longitude": 76.433,
    "capacity_kw": 56100,
    "ac_capacity_mw": 56.1,
    "hub_height_m": 80,
    "district": "Chitradurga",
    "status": "Active"
  },
  {
    "id": "wind_bannur",
    "name": "Bannur Wind Farm",
    "type": "wind",
    "latitude": 16.830,
    "longitude": 75.720,
    "capacity_kw": 78000,
    "ac_capacity_mw": 78.0,
    "hub_height_m": 120,
    "district": "Vijayapura",
    "status": "Active"
  },
  {
    "id": "wind_jogmatti",
    "name": "Jogmatti BSES Wind Farm",
    "type": "wind",
    "latitude": 14.108,
    "longitude": 76.391,
    "capacity_kw": 14000,
    "ac_capacity_mw": 14.0,
    "hub_height_m": 65,
    "district": "Chitradurga",
    "status": "Active"
  },
  {
    "id": "wind_bijapur",
    "name": "Bijapur Wind Farm",
    "type": "wind",
    "latitude": 16.750,
    "longitude": 75.900,
    "capacity_kw": 50000,
    "ac_capacity_mw": 50.0,
    "hub_height_m": 106,
    "district": "Vijayapura",
    "status": "Active"
  },
  {
    "id": "wind_gadag",
    "name": "Gadag Wind Farm",
    "type": "wind",
    "latitude": 15.420,
    "longitude": 75.620,
    "capacity_kw": 302400,
    "ac_capacity_mw": 302.4,
    "hub_height_m": 135,
    "district": "Gadag",
    "status": "Active"
  },
  {
    "id": "wind_mangoli",
    "name": "Energon Mangoli Wind Farm",
    "type": "wind",
    "latitude": 16.550,
    "longitude": 76.200,
    "capacity_kw": 46000,
    "ac_capacity_mw": 46.0,
    "hub_height_m": 100,
    "district": "Vijayapura",
    "status": "Active"
  },
  {
    "id": "wind_tata_power",
    "name": "Tata Power Wind Project",
    "type": "wind",
    "latitude": 15.350,
    "longitude": 75.580,
    "capacity_kw": 50400,
    "ac_capacity_mw": 50.4,
    "hub_height_m": 65,
    "district": "Gadag",
    "status": "Active"
  },
  {
    "id": "wind_clp",
    "name": "CLP Wind Farm",
    "type": "wind",
    "latitude": 16.140,
    "longitude": 74.830,
    "capacity_kw": 50000,
    "ac_capacity_mw": 50.0,
    "hub_height_m": 80,
    "district": "Belagavi",
    "status": "Active"
  }
]

def get_plants():
    return PLANTS

def get_plant_by_id(plant_id: str):
    return next((p for p in PLANTS if p["id"] == plant_id), None)
