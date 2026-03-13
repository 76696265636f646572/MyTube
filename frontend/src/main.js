import { createApp } from "vue";
import { addCollection } from "@iconify/vue";
import ui from "@nuxt/ui/vue-plugin";

import icons from "@iconify-json/lucide/icons.json";
import App from "./App.vue";
import { startWebsocketBus } from "./composables/websocketBus";
import { router } from "./router";
import "./css/style.css";

// Bundle Lucide icons locally (no runtime fetch from Iconify API)
// See: https://github.com/nuxt/icon?tab=readme-ov-file#iconify-dataset
addCollection(icons);

startWebsocketBus();

const app = createApp(App);
app.use(router);
app.use(ui);
app.mount("#app");
