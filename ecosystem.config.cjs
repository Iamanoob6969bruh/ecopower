module.exports = {
  apps: [
    {
      // Unified entrypoint: mounts the /api routes, the /sldc app, the scheduler
      // and the background scraper. (Previously pointed at src/api/main.py, which
      // is only the SLDC sub-app on port 8080 — no /api routes, no scheduler.)
      name: "eco-power-backend",
      script: "main.py",
      interpreter: "python",
      cwd: "backend",
      env: {
        PORT: "8000"
      }
    },
    {
      name: "eco-power-frontend",
      script: "node_modules/vite/bin/vite.js",
      cwd: "frontend",
      watch: false
    }
  ]
}
