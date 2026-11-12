const svg = (extra: string) =>
  "data:image/svg+xml," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="2" y="2" width="28" height="28" rx="6" fill="#0047ab"/><path d="M8 11h16M8 16h16M8 21h10" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>${extra}</svg>`,
  );

export const IDLE_ICON = svg("");
export const RECORDING_ICON = svg(
  '<circle cx="24" cy="24" r="7" fill="#e02424" stroke="#fff" stroke-width="2"/>',
);
