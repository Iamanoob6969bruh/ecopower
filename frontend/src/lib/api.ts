/**
 * Centralized API configuration for ECO POWER.
 * Automatically switches between production (Render) and local development.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Remove trailing slash if present
export const getBaseUrl = () => API_BASE_URL.replace(/\/$/, "");

export const API_ENDPOINTS = {
    SLDC_STATUS: `${getBaseUrl()}/sldc/status`,
    SOLAR_TOTAL: `${getBaseUrl()}/api/summary/total/solar`,
    WIND_TOTAL: `${getBaseUrl()}/api/summary/total/wind`,
    GENERATION_AGGREGATE: `${getBaseUrl()}/api/generation/aggregate/all`,
    PLANT_GENERATION: (plantId: string) => `${getBaseUrl()}/api/generation/${plantId}`,
    SLDC_GENERATION: `${getBaseUrl()}/sldc/generation`,
    SLDC_ASSETS: `${getBaseUrl()}/sldc/assets`,
    EXPLAIN_BLOCK: (plantId: string) => `${getBaseUrl()}/api/explain/${plantId}`,
    LIVE_PREDICTION: `${getBaseUrl()}/api/live-prediction`,
};
