import { onMounted, onUnmounted, ref } from "vue";

const MOBILE_MAX_WIDTH = 767;
/** Tailwind `xl` — right sidebar is in-flow (not overlay); toggle state is ignored for visibility. */
const XL_MIN_WIDTH = 1280;

function readIsMobile() {
  if (typeof window === "undefined") return false;
  return window.innerWidth <= MOBILE_MAX_WIDTH;
}

function readIsTabletLayout() {
  if (typeof window === "undefined") return false;
  const w = window.innerWidth;
  return w >= (MOBILE_MAX_WIDTH + 1) && w < XL_MIN_WIDTH;
}

export function useBreakpoint() {
  const isMobile = ref(readIsMobile());
  /** md–max-xl: floating right sidebar; queue/Sonos buttons toggle open + view. */
  const isTabletLayout = ref(readIsTabletLayout());

  function update() {
    if (typeof window === "undefined") return;
    isMobile.value = readIsMobile();
    isTabletLayout.value = readIsTabletLayout();
  }

  let mqlMobile;
  let mqlTablet;
  onMounted(() => {
    update();
    mqlMobile = window.matchMedia(`(max-width: ${MOBILE_MAX_WIDTH}px)`);
    mqlTablet = window.matchMedia(`(min-width: 768px) and (max-width: ${XL_MIN_WIDTH - 1}px)`);
    mqlMobile.addEventListener("change", update);
    mqlTablet.addEventListener("change", update);
  });
  onUnmounted(() => {
    if (mqlMobile) mqlMobile.removeEventListener("change", update);
    if (mqlTablet) mqlTablet.removeEventListener("change", update);
  });

  return { isMobile, isTabletLayout };
}
