import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import ui from "@nuxt/ui/vite";
import { resolve } from "path";

export default defineConfig({
  root: resolve(__dirname, "frontend"),
  plugins: [vue(), ui()],
  build: {
    outDir: resolve(__dirname, "app/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "frontend/index.html"),
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunks/[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "app.css";
          }
          return "assets/[name][extname]";
        }
      }
    }
  }
});
