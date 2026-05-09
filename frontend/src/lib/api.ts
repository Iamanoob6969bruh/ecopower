/**
 * Centralized API configuration for ECO POWER.
 * Automatically switches between production (Render) and local development.
 */

// Dynamic detection for Render vs Localhost
const getInitialBaseUrl = () => {
    // 1. Check for manual environment variable
    if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;
    
    // 2. If we are on Render, use your specific backend URL as a safety fallback
    if (typeof window !== "undefined") {
        if (window.location.hostname.includes("onrender.com")) {
            return "https://ecopower-backend.onrender.com";
        }
        if (window.location.hostname.includes("localhost")) {
            return "http://localhost:8000";
        }
    }
    
    return "http://localhost:8000";
};

const API_BASE_URL = getInitialBaseUrl();

// Debugging helper
if (typeof window !== "undefined") {
    console.log("🚀 ECO POWER API initialized at:", API_BASE_URL);
}

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
