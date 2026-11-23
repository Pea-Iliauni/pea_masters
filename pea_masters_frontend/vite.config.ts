import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    babel({ presets: [reactCompilerPreset()] })
  ],
  resolve:{
    alias:{
       "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // The FastAPI backend (pea_masters_backend). Going through this dev server keeps the app and the API on one
    // origin, so the httpOnly login cookie just works and Google redirects back to http://localhost:5173.
    // PEA_API_URL lets the end-to-end tests point a second dev server at their own backend
    proxy: { "/api": process.env.PEA_API_URL ?? "http://127.0.0.1:8000" },
  },
  // `vite preview` serves the production build. The end-to-end test of the Content Security Policy passes the
  // policy from deploy/Caddyfile here, so the built app is checked under exactly what the server sends.
  preview: {
    proxy: { "/api": process.env.PEA_API_URL ?? "http://127.0.0.1:8000" },
    headers: process.env.PEA_CSP ? { "Content-Security-Policy": process.env.PEA_CSP } : undefined,
  },
})
