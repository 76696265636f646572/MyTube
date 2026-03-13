import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import ui from "@nuxt/ui/vite";
import Pages from "vite-plugin-pages";
import { resolve } from "path";

// Icons: bundled via addCollection() in frontend/src/main.js using @iconify-json/lucide.
// See: https://github.com/nuxt/icon?tab=readme-ov-file#iconify-dataset

export default defineConfig({
  root: resolve(__dirname, "frontend"),
  plugins: [Pages({ dirs: "src/pages", extensions: ["vue"] }), vue(), ui()],
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
