module.exports = {
  apps: [
    {
      name: "eco-power-backend",
      script: "backend/src/api/main.py",
      interpreter: "python",
      env: {
        PYTHONPATH: "backend"
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
