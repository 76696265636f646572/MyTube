import { createApp } from "vue";
import ui from "@nuxt/ui/vue-plugin";

import App from "./App.vue";
import { router } from "./router";
import "./style.css";

const app = createApp(App);
app.use(router);
app.use(ui);
app.mount("#app");
